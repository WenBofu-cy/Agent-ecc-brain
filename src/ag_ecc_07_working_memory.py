#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-07
模块名称: 工作记忆模块
所属分区: 一、认知大脑核心模块
版本：V1.0（CPEC 最终合规版）
原创提出者：文波福

核心职责:
  短期上下文缓存中枢，提供临时数据存储与检索。
  会话结束或任务完成后自动清空，高价值数据沉淀至 ag-ecc-05。
  不参与推理或决策，仅提供数据的临时存储、检索与生命周期管理。

依赖模块: ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-05, ag-ecc-06, ag-ecc-08
被依赖模块: ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-06, ag-ecc-08

安全约束:
  W-01: 仅内存存储，不持久化
  W-02: 跨会话严格隔离
  W-03: 会话结束立即清除对话上下文和用户原始输入
  W-04: 沉淀数据经去个性化处理
  W-05: 不缓存安全令牌、密钥等
  W-06: 单会话条目硬上限
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_HIGH

logger = logging.getLogger("ag-ecc-07")

class MemoryState(Enum):
    NORMAL = "normal"
    CAPACITY_WARNING = "capacity_warning"
    SESSION_CLEANUP = "session_cleanup"
    SYSTEM_PAUSED = "system_paused"

class DataCategory(Enum):
    DIALOGUE_CONTEXT = "对话上下文"
    TASK_PROGRESS = "任务进度"
    TOOL_EVALUATION = "工具评估中间数据"
    REASONING_CHAIN = "推理链"
    PENDING_DECISION = "待确认决策候选"

@dataclass
class MemoryEntry:
    entry_id: str = ""
    data_category: DataCategory = DataCategory.DIALOGUE_CONTEXT
    payload: Dict[str, Any] = field(default_factory=dict)
    source_module: str = ""
    timestamp: float = field(default_factory=time.time)

class WorkingMemory:
    MAX_ENTRIES_PER_SESSION = 200
    SESSION_TIMEOUT_SEC = 1800
    STATUS_REPORT_INTERVAL_SEC = 60
    CATEGORY_MAX_ENTRIES = {
        DataCategory.DIALOGUE_CONTEXT: 50,
        DataCategory.TASK_PROGRESS: 100,
        DataCategory.TOOL_EVALUATION: 30,
        DataCategory.REASONING_CHAIN: 20,
        DataCategory.PENDING_DECISION: 10,
    }
    CATEGORY_MAX_SIZE_BYTES = {
        DataCategory.DIALOGUE_CONTEXT: 2 * 1024,
        DataCategory.TASK_PROGRESS: 1024,
        DataCategory.TOOL_EVALUATION: 3 * 1024,
        DataCategory.REASONING_CHAIN: 1024,
        DataCategory.PENDING_DECISION: 1024,
    }

    def __init__(self):
        self.module_id = "ag-ecc-07"
        self.version = "V1.0"
        self.state = MemoryState.NORMAL
        self.bus = None  # 由主入口注入 InternalBus

        self._sessions: Dict[str, Dict[DataCategory, List[MemoryEntry]]] = {}
        self._session_metadata: Dict[str, Dict[str, Any]] = {}
        self._total_entries = 0
        self._high_value_deposits = 0
        self._last_status_time = time.time()

        # 消息缓冲区（保留完整的 Message 对象以支持 correlation_id）
        self._write_requests: List[Message] = []
        self._query_requests: List[Message] = []
        self._session_end_notifications: List[Message] = []
        self._task_complete_notifications: List[Message] = []

        logger.info("工作记忆模块初始化完成")

    # ====================== 总线消息入口 ======================
    def handle_message(self, msg: Message):
        try:
            topic = msg.topic

            if topic.startswith("ag-ecc-07.write"):
                self._write_requests.append(msg)
            elif topic.startswith("ag-ecc-07.query"):
                self._query_requests.append(msg)
            elif topic == "ag-ecc-07.session_end":
                self._session_end_notifications.append(msg)
            elif topic == "ag-ecc-07.task_complete":
                self._task_complete_notifications.append(msg)
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()
            elif topic == "ag-ecc-12.resume":
                if self.state == MemoryState.SYSTEM_PAUSED:
                    self.state = MemoryState.NORMAL
                    logger.info("模块恢复服务")
        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    # ====================== CPEC 主循环 ======================
    def working_memory_main_loop(self):
        if self.state == MemoryState.SYSTEM_PAUSED:
            return

        now = time.time()

        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理所有缓冲消息
        while self._write_requests:
            self._handle_write_request(self._write_requests.pop(0), now)

        while self._query_requests:
            self._handle_query_request(self._query_requests.pop(0), now)

        while self._session_end_notifications:
            self._handle_session_end(self._session_end_notifications.pop(0))

        while self._task_complete_notifications:
            self._handle_task_complete(self._task_complete_notifications.pop(0))

        self._cleanup_idle_sessions(now)

    # ====================== 写入处理 ======================
    def _handle_write_request(self, msg: Message, now: float):
        data = msg.data
        session_id = data.get("session_id", "")
        category_str = data.get("data_category", "对话上下文")
        payload = data.get("payload", {})
        source_module = msg.source_module

        try:
            category = DataCategory(category_str)
        except Exception:
            category = DataCategory.DIALOGUE_CONTEXT

        max_bytes = self.CATEGORY_MAX_SIZE_BYTES.get(category, 2048)
        if len(str(payload)) > max_bytes:
            self._safe_send(source_module, "write_response", {
                "entry_id": "", "success": False, "error_reason": "数据超限"
            })
            return

        if session_id not in self._sessions:
            self._sessions[session_id] = {}
            self._session_metadata[session_id] = {
                "created_at": now, "last_active_at": now, "task_list": []
            }
        if category not in self._sessions[session_id]:
            self._sessions[session_id][category] = []

        session = self._sessions[session_id]
        total_entries = sum(len(lst) for lst in session.values())

        if total_entries >= self.MAX_ENTRIES_PER_SESSION * 0.8:
            self._gentle_cleanup(session_id)
            total_entries = sum(len(lst) for lst in session.values())

        if total_entries >= self.MAX_ENTRIES_PER_SESSION:
            self._safe_send(source_module, "write_response", {
                "entry_id": "", "success": False, "session_usage_pct": 1.0,
                "error_reason": "会话条目数已达硬上限"
            })
            return

        cat_list = session[category]
        if len(cat_list) >= self.CATEGORY_MAX_ENTRIES.get(category, 50):
            cat_list.pop(0)

        entry = MemoryEntry(
            entry_id=f"MEM-{uuid.uuid4().hex[:8]}",
            data_category=category,
            payload=payload,
            source_module=source_module,
            timestamp=now
        )
        cat_list.append(entry)
        self._session_metadata[session_id]["last_active_at"] = now

        usage_pct = total_entries / self.MAX_ENTRIES_PER_SESSION
        self._safe_send(source_module, "write_response", {
            "entry_id": entry.entry_id, "success": True,
            "session_usage_pct": round(usage_pct, 3)
        })

    # ====================== 查询处理（修复 correlation_id） ======================
    def _handle_query_request(self, msg: Message, now: float):
        data = msg.data
        session_id = data.get("session_id", "")
        scope_str = data.get("query_scope")
        max_results = data.get("max_results", 20)
        time_window = data.get("time_window_sec", 0)
        source_module = msg.source_module
        cid = msg.correlation_id  # 保留原始请求的 correlation_id

        results = []
        if session_id in self._sessions:
            for cat, entries in self._sessions[session_id].items():
                if scope_str is not None and cat.value != scope_str:
                    continue
                for entry in entries:
                    if time_window > 0 and (now - entry.timestamp) > time_window:
                        continue
                    results.append({
                        "entry_id": entry.entry_id,
                        "data_category": entry.data_category.value,
                        "payload": entry.payload,
                        "source_module": entry.source_module,
                        "timestamp": entry.timestamp
                    })

        results.sort(key=lambda x: x["timestamp"], reverse=True)
        results = results[:max_results]

        if self.bus:
            try:
                # 优先使用 publish_reply 支持同步请求
                self.bus.publish_reply(
                    topic=f"{source_module}.query_response",
                    source_module=self.module_id,
                    data={"session_id": session_id, "entries": results},
                    correlation_id=cid,
                    target_module=source_module
                )
            except Exception:
                # 降级为异步发布（兼容不支持 publish_reply 的总线）
                self.bus.publish_to_module(
                    target_module=source_module,
                    event_type="query_response",
                    source_module=self.module_id,
                    data={"session_id": session_id, "entries": results},
                    priority=PRIORITY_NORMAL,
                    correlation_id=cid
                )

    # ====================== 会话结束 ======================
    def _handle_session_end(self, msg: Message):
        session_id = msg.data.get("session_id", "")
        if session_id not in self._sessions:
            return

        high_value = self._extract_high_value(session_id)
        if high_value:
            self._safe_send("ag-ecc-05", "write_experience", {
                "entries": [{
                    "entry_id": e.entry_id,
                    "data_category": e.data_category.value,
                    "payload": e.payload,
                    "source_module": e.source_module,
                    "timestamp": e.timestamp
                } for e in high_value],
                "deposit_type": "session_end",
                "priority": 5
            })
            self._high_value_deposits += len(high_value)

        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._session_metadata:
            del self._session_metadata[session_id]

    # ====================== 任务完成清理 ======================
    def _handle_task_complete(self, msg: Message):
        plan_id = msg.data.get("plan_id", "")
        session_id = msg.data.get("associated_session_id", "")
        if not session_id or session_id not in self._sessions:
            return

        for cat in (DataCategory.TOOL_EVALUATION, DataCategory.REASONING_CHAIN, DataCategory.PENDING_DECISION):
            if cat in self._sessions[session_id]:
                self._sessions[session_id][cat] = [
                    e for e in self._sessions[session_id][cat]
                    if e.payload.get("plan_id") != plan_id
                ]

    # ====================== 容量与超时管理 ======================
    def _gentle_cleanup(self, session_id: str):
        if session_id not in self._sessions:
            return
        protected = {DataCategory.DIALOGUE_CONTEXT, DataCategory.TASK_PROGRESS}
        for cat, entries in self._sessions[session_id].items():
            if cat not in protected and entries:
                entries.pop(0)

    def _cleanup_idle_sessions(self, now: float):
        idle = [
            sid for sid, meta in self._session_metadata.items()
            if now - meta.get("last_active_at", 0) > self.SESSION_TIMEOUT_SEC
        ]
        for sid in idle:
            high_value = self._extract_high_value(sid)
            if high_value:
                self._safe_send("ag-ecc-05", "write_experience", {
                    "entries": [{
                        "entry_id": e.entry_id,
                        "data_category": e.data_category.value,
                        "payload": e.payload,
                        "source_module": e.source_module,
                        "timestamp": e.timestamp
                    } for e in high_value],
                    "deposit_type": "timeout",
                    "priority": 5
                })
                self._high_value_deposits += len(high_value)
            if sid in self._sessions:
                del self._sessions[sid]
            if sid in self._session_metadata:
                del self._session_metadata[sid]

    def _extract_high_value(self, session_id: str) -> List[MemoryEntry]:
        high = []
        if session_id not in self._sessions:
            return high
        sensitive_keys = {"user_id", "session_id", "token", "password"}
        for cat in (DataCategory.TASK_PROGRESS, DataCategory.REASONING_CHAIN):
            for entry in self._sessions[session_id].get(cat, []):
                cleaned = {k: v for k, v in entry.payload.items() if k not in sensitive_keys}
                high.append(MemoryEntry(
                    entry_id=entry.entry_id,
                    data_category=entry.data_category,
                    payload=cleaned,
                    source_module=entry.source_module,
                    timestamp=entry.timestamp
                ))
        return high

    # ====================== 通信与状态 ======================
    def _safe_send(self, target: str, event_type: str, data: dict):
        """安全发送消息，忽略总线异常"""
        if not self.bus:
            return
        try:
            self.bus.publish_to_module(
                target_module=target,
                event_type=event_type,
                source_module=self.module_id,
                data=data,
                priority=PRIORITY_NORMAL
            )
        except Exception:
            pass

    def _publish_status(self):
        if not self.bus:
            return
        total_entries = sum(
            sum(len(lst) for lst in sess.values())
            for sess in self._sessions.values()
        )
        active = len(self._sessions)
        usage = total_entries / max(active * self.MAX_ENTRIES_PER_SESSION, 1)
        try:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="memory_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "active_sessions": active,
                    "total_entries": total_entries,
                    "total_usage_pct": round(min(usage, 1.0), 3),
                    "high_value_deposits": self._high_value_deposits
                },
                priority=PRIORITY_LOW
            )
        except Exception:
            pass

    def emergency_shutdown(self):
        self.state = MemoryState.SYSTEM_PAUSED
        logger.info("工作记忆模块已暂停")

    def get_state(self) -> MemoryState:
        return self.state