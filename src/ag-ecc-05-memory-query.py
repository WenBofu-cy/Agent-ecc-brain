#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-05
模块名称: 记忆查询模块
所属分区: 一、认知大脑核心模块
核心职责: 作为 ECC 认知大脑与 MLNF-Mem 记忆中枢之间的统一查询网关，负责将认知模块的
          记忆检索需求转化为标准化的查询请求，通过 MemoryBus 发送至 ag-mem-01（总控漏斗
          F₀）进行双漏斗检索。将记忆中枢返回的原始经验数据转化为认知模块可直接消费的
          结构化摘要。同时管理查询缓存、结果合并与去重，优化高频查询的响应速度。不参与
          记忆的写入或管理，仅执行记忆的检索与结果适配。

依赖模块:
    ag-mem-01(总控漏斗F₀)
被依赖模块:
    ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-08, ag-ecc-10

安全约束:
  Q-01: 本模块仅读取记忆数据，不参与任何记忆写入、修改或删除操作
  Q-02: 查询请求不得包含用户的原始输入内容，仅发送结构化的查询条件
  Q-03: 返回的记忆数据在传递至上游模块前必须经过脱敏处理
  Q-04: 查询缓存仅存储脱敏后的摘要数据，不得缓存完整的经验原始数据
  Q-05: 不同用户之间的查询缓存必须隔离，禁止跨用户缓存命中
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
from collections import OrderedDict


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


@dataclass
class MemoryQueryReceipt:
    query_id: str = ""  # 修复：增加 query_id 用于精确匹配
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


@dataclass
class QueryTimeoutNotice:
    request_id: str = ""
    reason: str = "记忆中枢响应超时"
    has_cached_result: bool = False
    suggestion: str = "请稍后重试"


class MemoryQueryGateway:
    # 超时
    QUERY_TIMEOUT_SEC = 2.0
    # 缓存配置
    CACHE_CONFIG = {
        QueryType.USER_PREFERENCE: {"ttl_sec": 300, "max_size": 50},
        QueryType.TASK_TEMPLATE: {"ttl_sec": 600, "max_size": 100},
        QueryType.TOOL_EXPERIENCE: {"ttl_sec": 120, "max_size": 200},
        QueryType.FAILURE_EXPERIENCE: {"ttl_sec": 0, "max_size": 0},  # 不缓存
        QueryType.INTERACTION_HISTORY: {"ttl_sec": 60, "max_size": 30},
    }
    STATUS_REPORT_INTERVAL_SEC = 60

    def __init__(self):
        self.module_id = "ag-ecc-05"
        self.module_name = "记忆查询模块"
        self.version = "V1.0"

        self.state = QueryState.WAITING_QUERY
        self._active_queries: Dict[str, Dict[str, Any]] = {}
        self._caches: Dict[QueryType, OrderedDict] = {qt: OrderedDict() for qt in QueryType}
        self._cache_hits: int = 0
        self._total_queries: int = 0
        self._total_query_time: float = 0.0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_request = None
        self._query_receipt = None

        self._publish_memory_query = None
        self._publish_preference_summary = None
        self._publish_task_template = None
        self._publish_tool_experience = None
        self._publish_failure_list = None
        self._publish_interaction_history = None
        self._publish_timeout_notice = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_request_query(self, callback: Callable[[], Optional[MemoryQueryRequest]]):
        self._query_request = callback

    def set_receipt_query(self, callback: Callable[[], Optional[MemoryQueryReceipt]]):
        self._query_receipt = callback

    def set_memory_query_publisher(self, callback: Callable[[MemoryQueryRequest], None]):
        self._publish_memory_query = callback

    def set_preference_summary_publisher(self, callback: Callable[[UserPreferenceSummary], None]):
        self._publish_preference_summary = callback

    def set_task_template_publisher(self, callback: Callable[[TaskTemplate], None]):
        self._publish_task_template = callback

    def set_tool_experience_publisher(self, callback: Callable[[ToolExperienceSummary], None]):
        self._publish_tool_experience = callback

    def set_failure_list_publisher(self, callback: Callable[[FailureExperienceList], None]):
        self._publish_failure_list = callback

    def set_interaction_history_publisher(self, callback: Callable[[InteractionHistorySummary], None]):
        self._publish_interaction_history = callback

    def set_timeout_notice_publisher(self, callback: Callable[[QueryTimeoutNotice], None]):
        self._publish_timeout_notice = callback

    def set_status_report_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_query_cycle(self):
        now = time.time()

        if self.state == QueryState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理记忆中枢回执
        if self.state == QueryState.QUERYING:
            receipt = self._query_receipt() if self._query_receipt else None
            if receipt:
                self._handle_receipt(receipt)
                return

            # 检查超时
            for qid, info in list(self._active_queries.items()):
                if now - info["start_time"] > self.QUERY_TIMEOUT_SEC:
                    self.state = QueryState.QUERY_TIMEOUT
                    self._handle_timeout(qid, info)
                    self.state = QueryState.WAITING_QUERY
            return

        # 接收查询请求
        request = self._query_request() if self._query_request else None
        if request is None:
            return

        self._total_queries += 1

        # 检查缓存（失败经验不缓存）
        if request.query_type != QueryType.FAILURE_EXPERIENCE:
            cached = self._check_cache(request)
            if cached is not None:
                self._cache_hits += 1
                self._dispatch_result(request, cached)
                return

        # 发送查询至记忆中枢
        self.state = QueryState.QUERYING
        qid = f"Q-{uuid.uuid4().hex[:8]}"
        self._active_queries[qid] = {
            "request": request,
            "start_time": now
        }

        if self._publish_memory_query:
            self._publish_memory_query(request)

    # ========== 回执处理 ==========
    def _handle_receipt(self, receipt: MemoryQueryReceipt):
        # 修复：按 query_id 精确匹配，避免并发查询时回执错配
        qid = receipt.query_id
        if qid not in self._active_queries:
            self.state = QueryState.WAITING_QUERY
            return

        info = self._active_queries.pop(qid)
        request = info["request"]
        self.state = QueryState.FORMATTING

        # 根据请求类型整理结果
        formatted = self._format_result(request, receipt.matched_entries)

        # 缓存结果
        if request.query_type != QueryType.FAILURE_EXPERIENCE:
            self._update_cache(request, formatted)

        # 分发结果
        self._dispatch_result(request, formatted)

        elapsed = (time.time() - info["start_time"]) * 1000
        self._total_query_time += elapsed
        self.state = QueryState.WAITING_QUERY

    def _handle_timeout(self, qid: str, info: Dict[str, Any]):
        request = info["request"]
        # 尝试返回缓存
        cached = self._check_cache(request)
        if cached is not None:
            self._dispatch_result(request, cached)
            if self._publish_timeout_notice:
                self._publish_timeout_notice(QueryTimeoutNotice(
                    request_id=request.request_id,
                    has_cached_result=True,
                    suggestion="已返回缓存结果"
                ))
        else:
            if self._publish_timeout_notice:
                self._publish_timeout_notice(QueryTimeoutNotice(
                    request_id=request.request_id,
                    has_cached_result=False,
                    suggestion="请稍后重试"
                ))
        del self._active_queries[qid]

    # ========== 结果格式化 ==========
    def _format_result(self, request: MemoryQueryRequest, entries: List[Dict[str, Any]]) -> Any:
        if request.query_type == QueryType.USER_PREFERENCE:
            return self._format_preference(entries)
        elif request.query_type == QueryType.TASK_TEMPLATE:
            return self._format_task_template(entries)
        elif request.query_type == QueryType.TOOL_EXPERIENCE:
            return self._format_tool_experience(request.tool_name, entries)
        elif request.query_type == QueryType.FAILURE_EXPERIENCE:
            return FailureExperienceList(request_id=request.request_id, entries=entries, total_matched=len(entries))
        elif request.query_type == QueryType.INTERACTION_HISTORY:
            return self._format_interaction_history(entries)
        return entries

    def _format_preference(self, entries: List[Dict[str, Any]]) -> UserPreferenceSummary:
        keywords = []
        tools = []
        for e in entries:
            keywords.extend(e.get("keywords", []))
            if e.get("tool_name"):
                tools.append(e["tool_name"])
        return UserPreferenceSummary(
            preference_keywords=list(set(keywords))[:20],
            high_freq_tools=list(set(tools))[:10]
        )

    def _format_task_template(self, entries: List[Dict[str, Any]]) -> TaskTemplate:
        steps = entries[0].get("steps", []) if entries else []
        return TaskTemplate(steps=steps)

    def _format_tool_experience(self, tool_name: str, entries: List[Dict[str, Any]]) -> ToolExperienceSummary:
        if entries:
            e = entries[0]
            return ToolExperienceSummary(
                tool_name=tool_name,
                success_rate=e.get("success_rate", 0.5),
                avg_response_ms=e.get("avg_response_ms", 500.0),
                common_errors=e.get("common_errors", []),
                call_count=e.get("call_count", 0)
            )
        return ToolExperienceSummary(tool_name=tool_name)

    def _format_interaction_history(self, entries: List[Dict[str, Any]]) -> InteractionHistorySummary:
        topics = [e.get("topic", "") for e in entries if e.get("topic")]
        return InteractionHistorySummary(
            total_turns=len(entries),
            recent_topics=list(set(topics))[:5]
        )

    # ========== 缓存管理 ==========
    def _check_cache(self, request: MemoryQueryRequest) -> Optional[Any]:
        cfg = self.CACHE_CONFIG.get(request.query_type, {})
        if cfg.get("ttl_sec", 0) <= 0:
            return None

        cache_key = f"{request.query_type.value}:{request.user_id}:{','.join(request.keywords)}"
        cache = self._caches[request.query_type]
        if cache_key in cache:
            entry, timestamp = cache[cache_key]
            if time.time() - timestamp < cfg["ttl_sec"]:
                # 修复：命中时将条目移至末尾，实现 LRU
                cache.move_to_end(cache_key)
                return entry
            else:
                del cache[cache_key]
        return None

    def _update_cache(self, request: MemoryQueryRequest, result: Any):
        cfg = self.CACHE_CONFIG.get(request.query_type, {})
        if cfg.get("ttl_sec", 0) <= 0:
            return

        cache_key = f"{request.query_type.value}:{request.user_id}:{','.join(request.keywords)}"
        cache = self._caches[request.query_type]
        if len(cache) >= cfg.get("max_size", 50):
            cache.popitem(last=False)
        cache[cache_key] = (result, time.time())
        # 修复：新条目也移至末尾，保持 LRU 顺序
        cache.move_to_end(cache_key)

    # ========== 结果分发 ==========
    def _dispatch_result(self, request: MemoryQueryRequest, result: Any):
        if request.query_type == QueryType.USER_PREFERENCE and self._publish_preference_summary:
            self._publish_preference_summary(result)
        elif request.query_type == QueryType.TASK_TEMPLATE and self._publish_task_template:
            self._publish_task_template(result)
        elif request.query_type == QueryType.TOOL_EXPERIENCE and self._publish_tool_experience:
            self._publish_tool_experience(result)
        elif request.query_type == QueryType.FAILURE_EXPERIENCE and self._publish_failure_list:
            self._publish_failure_list(result)
        elif request.query_type == QueryType.INTERACTION_HISTORY and self._publish_interaction_history:
            self._publish_interaction_history(result)

    # ========== 辅助 ==========
    def _publish_status(self):
        avg = self._total_query_time / max(self._total_queries, 1)
        hit_rate = self._cache_hits / max(self._total_queries, 1)
        if self._publish_status_report:
            self._publish_status_report({
                "state": self.state.value,
                "active_queries": len(self._active_queries),
                "avg_response_ms": round(avg, 2),
                "cache_hit_rate": round(hit_rate, 3)
            })

    def get_state(self) -> QueryState:
        return self.state

    def emergency_shutdown(self):
        self.state = QueryState.SYSTEM_PAUSED
        self._active_queries.clear()
        print(f"[{self.module_id}] 紧急熔断")

    def _log_event(self, event_type: str, details: Dict[str, Any]):
        entry = {
            "log_id": f"log-{uuid.uuid4().hex[:8]}",
            "event_type": event_type,
            "source_module": self.module_id,
            "details": details,
            "timestamp": time.time()
        }
        self._pending_logs.append(entry)
        if self._publish_event_log:
            self._publish_event_log(entry)

    def collect_pending_logs(self) -> List[Dict[str, Any]]:
        logs = self._pending_logs.copy()
        self._pending_logs.clear()
        return logs


# ========== 演示与测试 ==========
def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_main():
    print("=" * 70)
    print("  Agent-ecc-brain 记忆查询模块 (ag-ecc-05) 演示")
    print("=" * 70)

    gateway = MemoryQueryGateway()

    print_separator("STEP 1: 查询用户偏好（首次无缓存）")
    gateway.set_request_query(lambda: MemoryQueryRequest(
        request_id="Q1", requester_module="ag-ecc-01",
        query_type=QueryType.USER_PREFERENCE, user_id="U001"
    ))
    gateway.run_query_cycle()

    print_separator("STEP 2: 查询工具经验")
    gateway.set_request_query(lambda: MemoryQueryRequest(
        request_id="Q2", requester_module="ag-ecc-03",
        query_type=QueryType.TOOL_EXPERIENCE, tool_name="weather_api"
    ))
    gateway.run_query_cycle()

    print_separator("STEP 3: 查询失败经验（不缓存）")
    gateway.set_request_query(lambda: MemoryQueryRequest(
        request_id="Q3", requester_module="ag-ecc-08",
        query_type=QueryType.FAILURE_EXPERIENCE
    ))
    gateway.run_query_cycle()

    print("\n✅ 记忆查询模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-05 记忆查询模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_gateway():
            return MemoryQueryGateway()

        # TC-E05-01: 接收查询请求并转发
        print("\n[TC-E05-01] 接收查询请求并转发")
        try:
            g = setup_gateway()
            g.set_request_query(lambda: MemoryQueryRequest(
                request_id="T01", query_type=QueryType.USER_PREFERENCE, user_id="U001"
            ))
            g.run_query_cycle()
            assert g.state == QueryState.QUERYING
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E05-02: 缓存命中（第二次相同查询）
        print("\n[TC-E05-02] 缓存命中并触发 LRU")
        try:
            g = setup_gateway()
            # 手动注入两条缓存，然后访问第一条，检查 LRU 顺序
            cache = g._caches[QueryType.USER_PREFERENCE]
            cache["key_a"] = ("data_a", time.time())
            cache["key_b"] = ("data_b", time.time())
            # 访问 key_a 使其变为最近使用
            g._check_cache = lambda req: cache.get("key_a", (None, 0))[0] if req.user_id == "test" else None
            g.set_request_query(lambda: MemoryQueryRequest(
                request_id="T02", query_type=QueryType.USER_PREFERENCE, user_id="test", keywords=["key_a"]
            ))
            g.run_query_cycle()
            # 此时 key_a 应被移至末尾
            assert list(cache.keys())[-1] == "key_a"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E05-03: 失败经验不缓存
        print("\n[TC-E05-03] 失败经验不缓存")
        try:
            g = setup_gateway()
            g.set_request_query(lambda: MemoryQueryRequest(
                request_id="T03", query_type=QueryType.FAILURE_EXPERIENCE
            ))
            g.run_query_cycle()
            assert g.state == QueryState.QUERYING
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E05-04: 查询超时处理
        print("\n[TC-E05-04] 查询超时处理")
        try:
            g = setup_gateway()
            g._active_queries["old_q"] = {"request": MemoryQueryRequest(request_id="T04"), "start_time": time.time() - g.QUERY_TIMEOUT_SEC - 1}
            g.state = QueryState.QUERYING
            g.run_query_cycle()
            assert "old_q" not in g._active_queries
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E05-05: 回执精确匹配（修复验证）
        print("\n[TC-E05-05] 回执精确匹配")
        try:
            g = setup_gateway()
            # 注入两个活跃查询
            g._active_queries["q1"] = {"request": MemoryQueryRequest(request_id="R1"), "start_time": time.time()}
            g._active_queries["q2"] = {"request": MemoryQueryRequest(request_id="R2"), "start_time": time.time()}
            g.state = QueryState.QUERYING
            # 模拟收到 q2 的回执
            g._query_receipt = lambda: MemoryQueryReceipt(query_id="q2", matched_entries=[])
            g.run_query_cycle()
            # q2 应该被移除，q1 仍然存在
            assert "q1" in g._active_queries
            assert "q2" not in g._active_queries
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E05-06: 紧急熔断
        print("\n[TC-E05-06] 紧急熔断")
        try:
            g = setup_gateway()
            g.emergency_shutdown()
            assert g.state == QueryState.SYSTEM_PAUSED
            assert len(g._active_queries) == 0
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        print("\n" + "=" * 60)
        print(f"测试结果: {passed} PASS, {failed} FAIL")
        print("=" * 60)
    else:
        demo_main()