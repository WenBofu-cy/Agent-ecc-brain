#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-05
模块名称: 记忆查询模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责:
  作为 ECC 认知大脑与 MLNF-Mem 记忆中枢之间的统一查询网关，负责将认知模块的
  记忆检索需求转化为标准化的查询请求，通过 MemoryBus 经由 ag-ecc-12 发送至
  ag-mem-01（总控漏斗F₀）进行双漏斗检索。将记忆中枢返回的原始经验数据转化为
  认知模块可直接消费的结构化摘要。同时管理查询缓存、结果合并与去重，优化高频
  查询的响应速度。不参与记忆的写入或管理，仅执行记忆的检索与结果适配。

依赖模块:
  ag-mem-01(总控漏斗F₀), ag-ecc-12(资源调度模块, 作为对外网关)
被依赖模块:
  ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-08, ag-ecc-10

安全约束:
  Q-01: 本模块仅读取记忆数据，不参与任何记忆写入、修改或删除操作
  Q-02: 查询请求不得包含用户的原始输入内容，仅发送结构化的查询条件
  Q-03: 返回的记忆数据在传递至上游模块前必须经过脱敏处理
  Q-04: 查询缓存仅存储脱敏后的摘要数据，不得缓存完整的经验原始数据
  Q-05: 不同用户之间的查询缓存必须隔离，禁止跨用户缓存命中
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging
from collections import OrderedDict

# 标准总线导入（与主系统完全一致）
from memory_bus import Message, PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-05")

# ==================== 状态与类型定义 ====================
class QueryState(Enum):
    WAITING_QUERY = "waiting_query"
    QUERYING = "querying"
    FORMATTING = "formatting"
    QUERY_TIMEOUT = "query_timeout"
    SYSTEM_PAUSED = "system_paused"

class QueryType(Enum):
    USER_PREFERENCE = "用户偏好"
    TASK_TEMPLATE = "历史任务模板"
    TOOL_EXPERIENCE = "工具经验"
    FAILURE_EXPERIENCE = "失败经验"
    INTERACTION_HISTORY = "交互历史"

@dataclass
class MemoryQueryRequest:
    request_id: str = ""
    requester_module: str = ""
    query_type: QueryType = QueryType.USER_PREFERENCE
    user_id: str = ""
    session_id: str = ""
    keywords: List[str] = field(default_factory=list)
    task_type: str = ""
    tool_name: str = ""
    time_window_hours: int = 168
    max_results: int = 20
    only_success: bool = False
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryQueryRequest":
        try:
            data = data.copy()
            if "query_type" in data and isinstance(data["query_type"], str):
                data["query_type"] = QueryType(data["query_type"])
            fields = {f.name for f in cls.__dataclass_fields__.values()}
            return cls(**{k: v for k, v in data.items() if k in fields})
        except Exception:
            return cls()

@dataclass
class MemoryQueryReceipt:
    query_id: str = ""
    matched_entries: List[Dict[str, Any]] = field(default_factory=list)
    source_funnel: str = ""
    query_duration_ms: float = 0.0

@dataclass
class UserPreferenceSummary:
    user_id: str = ""
    preference_keywords: List[str] = field(default_factory=list)
    high_freq_tools: List[str] = field(default_factory=list)
    scene_distribution: Dict[str, float] = field(default_factory=dict)
    preference_strength_vector: List[float] = field(default_factory=list)

@dataclass
class TaskTemplate:
    request_id: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    success_rate: float = 0.0
    avg_duration_sec: float = 0.0
    is_exact_match: bool = False

@dataclass
class ToolExperienceSummary:
    request_id: str = ""
    tool_name: str = ""
    success_rate: float = 0.5
    avg_response_ms: float = 500.0
    common_errors: List[str] = field(default_factory=list)
    call_count: int = 0

@dataclass
class FailureExperienceList:
    request_id: str = ""
    entries: List[Dict[str, Any]] = field(default_factory=list)
    total_matched: int = 0

@dataclass
class InteractionHistorySummary:
    request_id: str = ""
    total_turns: int = 0
    recent_topics: List[str] = field(default_factory=list)
    emotion_trend: str = "稳定"
    interaction_pace_preference: str = "正常"

class MemoryQueryGateway:
    """记忆查询模块 V1.0（生产标准定稿）"""

    QUERY_TIMEOUT_SEC = 2.0
    STATUS_REPORT_INTERVAL_SEC = 60

    # 各类查询缓存配置
    CACHE_CONFIG = {
        QueryType.USER_PREFERENCE: {"ttl_sec": 300, "max_size": 50},
        QueryType.TASK_TEMPLATE: {"ttl_sec": 600, "max_size": 100},
        QueryType.TOOL_EXPERIENCE: {"ttl_sec": 120, "max_size": 200},
        QueryType.FAILURE_EXPERIENCE: {"ttl_sec": 0, "max_size": 0},
        QueryType.INTERACTION_HISTORY: {"ttl_sec": 60, "max_size": 30},
    }

    # 敏感字段（脱敏 Q-03）
    SENSITIVE_FIELDS = {"user_id", "session_id", "raw_input", "original_text", "device_id"}

    def __init__(self):
        self.module_id = "ag-ecc-05"
        self.version = "V1.0"
        self.state = QueryState.WAITING_QUERY
        self.bus = None  # 由主入口注入

        # 活跃查询 & 缓冲区
        self._active_queries: Dict[str, Dict[str, Any]] = {}
        self._request_buffer: List[Dict[str, Any]] = []
        self._receipt_buffer: List[MemoryQueryReceipt] = []

        # 缓存（用户隔离 Q-05）
        self._caches: Dict[QueryType, OrderedDict] = {qt: OrderedDict() for qt in QueryType}

        # 统计
        self._total_queries = 0
        self._cache_hits = 0
        self._total_query_time = 0.0
        self._last_status_time = time.time()

        logger.info("记忆查询模块初始化完成")

    # ====================== 标准总线消息入口 ======================
    def handle_message(self, msg: Message):
        try:
            topic = msg.topic

            # 查询请求入队
            if topic.startswith("ag-ecc-05.query_"):
                self._request_buffer.append({
                    "data": msg.data,
                    "source_module": msg.source_module,
                    "correlation_id": msg.correlation_id,  # 直接使用属性
                    "topic": topic
                })

            # 记忆查询回执
            elif topic == "ag-ecc-05.memory_receipt":
                d = msg.data
                self._receipt_buffer.append(MemoryQueryReceipt(
                    query_id=d.get("query_id", ""),
                    matched_entries=d.get("matched_entries", []),
                    source_funnel=d.get("source_funnel", ""),
                    query_duration_ms=d.get("query_duration_ms", 0.0)
                ))

            # 停机 / 恢复
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-05.shutdown"):
                self.emergency_shutdown()
            elif topic == "ag-ecc-05.resume":
                if self.state == QueryState.SYSTEM_PAUSED:
                    self.state = QueryState.WAITING_QUERY
                    logger.info("记忆查询模块已恢复服务")

        except Exception as e:
            logger.error(f"消息处理异常: {str(e)}", exc_info=True)

    # ====================== CPEC 标准主循环 ======================
    def memory_query_main_loop(self):
        if self.state == QueryState.SYSTEM_PAUSED:
            return

        now = time.time()
        self._process_receipts()
        self._check_timeouts(now)
        self._process_requests(now)

        # 定时状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

    # ====================== 核心流程 ======================
    def _process_requests(self, now):
        while self._request_buffer and self.state == QueryState.WAITING_QUERY:
            self._handle_single_query(self._request_buffer.pop(0), now)

    def _handle_single_query(self, item: Dict[str, Any], now: float):
        data = item["data"]
        src = item["source_module"]
        cid = item["correlation_id"]
        req = MemoryQueryRequest.from_dict(data)
        self._total_queries += 1

        # 缓存命中（用户隔离 Q-05）
        cached = self._get_from_cache(req)
        if cached is not None:
            self._cache_hits += 1
            self._send_response(src, req, cached, cid)
            return

        # 发送到 ag-ecc-12 转发记忆查询
        self.state = QueryState.QUERYING
        qid = f"Q-{uuid.uuid4().hex[:8]}"
        self._active_queries[qid] = {
            "request": req,
            "source_module": src,
            "correlation_id": cid,
            "start_time": now
        }

        if self.bus:
            self.bus.publish(
                topic="ag-ecc-12.memory_query",
                source_module=self.module_id,
                data={
                    "query_id": qid,
                    "query_type": req.query_type.value,
                    "user_id": req.user_id,
                    "keywords": req.keywords,
                    "tool_name": req.tool_name,
                    "task_type": req.task_type
                },
                target_module="ag-ecc-12",
                correlation_id=cid,
            )

    def _process_receipts(self):
        while self._receipt_buffer:
            receipt = self._receipt_buffer.pop(0)
            info = self._active_queries.pop(receipt.query_id, None)
            if not info:
                continue

            req = info["request"]
            src = info["source_module"]
            cid = info["correlation_id"]
            self.state = QueryState.FORMATTING

            # 脱敏 Q-03
            cleaned = self._sanitize_batch(receipt.matched_entries)
            result = self._build_structured_result(req, cleaned)

            # 写入缓存（仅摘要 Q-04）
            self._save_to_cache(req, result)
            self._send_response(src, req, result, cid)
            self.state = QueryState.WAITING_QUERY

    def _check_timeouts(self, now):
        expired = [q for q, i in self._active_queries.items()
                   if now - i["start_time"] > self.QUERY_TIMEOUT_SEC]
        for qid in expired:
            info = self._active_queries.pop(qid)
            req = info["request"]
            fallback = self._get_from_cache(req)
            if fallback:
                self._send_response(info["source_module"], req, fallback, info["correlation_id"])
            self.state = QueryState.QUERY_TIMEOUT
            logger.warning(f"查询超时，已尝试使用缓存兜底: {qid}")

    # ====================== 脱敏（Q-03） ======================
    def _sanitize_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in entry.items():
            if k in self.SENSITIVE_FIELDS:
                out[k] = "ANONYMIZED" if k != "raw_input" else "[REDACTED]"
            else:
                out[k] = v
        return out

    def _sanitize_batch(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self._sanitize_entry(e) for e in entries]

    # ====================== 结果结构化 ======================
    def _build_structured_result(self, req: MemoryQueryRequest, entries: List[Dict[str, Any]]):
        if req.query_type == QueryType.USER_PREFERENCE:
            return self._build_preference(entries)
        elif req.query_type == QueryType.TASK_TEMPLATE:
            return TaskTemplate(steps=entries[0].get("steps", []) if entries else [])
        elif req.query_type == QueryType.TOOL_EXPERIENCE:
            return self._build_tool_exp(req.tool_name, entries)
        elif req.query_type == QueryType.FAILURE_EXPERIENCE:
            return FailureExperienceList(entries=entries, total_matched=len(entries))
        elif req.query_type == QueryType.INTERACTION_HISTORY:
            return InteractionHistorySummary(total_turns=len(entries))
        return entries

    def _build_preference(self, entries):
        kw, tools = set(), set()
        for e in entries:
            kw.update(e.get("keywords", []))
            tools.add(e.get("tool_name", ""))
        return UserPreferenceSummary(
            preference_keywords=list(kw)[:20],
            high_freq_tools=list(tools - {""})[:10]
        )

    def _build_tool_exp(self, name, entries):
        if not entries:
            return ToolExperienceSummary(tool_name=name)
        e = entries[0]
        return ToolExperienceSummary(
            tool_name=name,
            success_rate=e.get("success_rate", 0.5),
            avg_response_ms=e.get("avg_response_ms", 500),
            common_errors=e.get("common_errors", []),
            call_count=e.get("call_count", 0)
        )

    # ====================== 缓存（Q-04 / Q-05） ======================
    def _get_from_cache(self, req: MemoryQueryRequest) -> Optional[Any]:
        cfg = self.CACHE_CONFIG.get(req.query_type)
        if not cfg or cfg["ttl_sec"] <= 0:
            return None

        # 关键字列表为空时，join 生成空字符串，缓存 Key 唯一性已保证
        key = f"{req.query_type.value}:{req.user_id}:{','.join(req.keywords)}"
        cache = self._caches[req.query_type]
        if key not in cache:
            return None

        val, ts = cache[key]
        if time.time() - ts > cfg["ttl_sec"]:
            del cache[key]
            return None

        cache.move_to_end(key)
        return val

    def _save_to_cache(self, req, result):
        cfg = self.CACHE_CONFIG.get(req.query_type)
        if not cfg or cfg["ttl_sec"] <= 0:
            return

        key = f"{req.query_type.value}:{req.user_id}:{','.join(req.keywords)}"
        cache = self._caches[req.query_type]
        if len(cache) >= cfg["max_size"]:
            cache.popitem(last=False)
        cache[key] = (result, time.time())

    # ====================== 通信 ======================
    def _send_response(self, target: str, req: MemoryQueryRequest, res: Any, cid: str = ""):
        type_map = {
            QueryType.USER_PREFERENCE: "preference_summary",
            QueryType.TASK_TEMPLATE: "task_template",
            QueryType.TOOL_EXPERIENCE: "tool_experience",
            QueryType.FAILURE_EXPERIENCE: "failure_list",
            QueryType.INTERACTION_HISTORY: "interaction_history"
        }
        evt = type_map.get(req.query_type)
        if not evt or not self.bus:
            return

        self.bus.publish(
            topic=f"{target}.{evt}",
            source_module=self.module_id,
            data=res.__dict__ if hasattr(res, "__dict__") else {},
            target_module=target,
            correlation_id=cid,
        )

    def _publish_status(self):
        if not self.bus:
            return
        avg = self._total_query_time / max(self._total_queries, 1)
        hit_rate = self._cache_hits / max(self._total_queries, 1)
        self.bus.publish(
            topic="ag-ecc-12.memory_query_status",
            source_module=self.module_id,
            data={
                "state": self.state.value,
                "active_queries": len(self._active_queries),
                "avg_query_ms": round(avg, 2),
                "cache_hit_rate": round(hit_rate, 3)
            },
            target_module="ag-ecc-12"
        )

    # ====================== 停机 ======================
    def emergency_shutdown(self):
        self.state = QueryState.SYSTEM_PAUSED
        self._active_queries.clear()
        logger.info("记忆查询模块已暂停（系统熔断）")

    def get_state(self) -> QueryState:
        return self.state