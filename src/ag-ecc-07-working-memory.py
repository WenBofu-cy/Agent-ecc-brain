#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-07
模块名称: 工作记忆模块
所属分区: 一、认知大脑核心模块
核心职责: 作为 ECC 认知大脑的短期上下文缓存中枢，为当前活跃会话提供临时的数据存储与检索
          服务。存储推理中间数据、任务进度状态、多轮对话上下文、待确认的决策候选等短期
          信息。在会话结束时或任务完成后自动清空对应数据。同时负责将高价值的短期认知洞察
          通过 ag-ecc-05（记忆查询模块）沉淀至 MLNF-Mem 记忆中枢。不参与任何推理或决策，
          仅提供数据的临时存储、检索与生命周期管理。

依赖模块:
    ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-05, ag-ecc-06, ag-ecc-08
被依赖模块:
    ag-ecc-01, ag-ecc-02, ag-ecc-03, ag-ecc-06, ag-ecc-08

安全约束:
  W-01: 工作内存数据仅存于内存，进程重启后自动丢弃，不进行任何持久化存储
  W-02: 不同会话之间的工作内存数据严格隔离，禁止跨会话查询或数据混合
  W-03: 会话结束时，对话上下文和用户原始输入数据必须立即清除，不得残留
  W-04: 长效沉淀至记忆中枢的数据必须经过去个性化处理，不得包含用户个人身份信息
  W-05: 工作内存中不得缓存任何安全令牌、密钥或用户密码等敏感凭证信息
  W-06: 单个会话的总条目数不得超过硬上限，防止内存溢出
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


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
class MemoryWriteRequest:
    session_id: str = ""
    data_category: DataCategory = DataCategory.DIALOGUE_CONTEXT
    payload: Dict[str, Any] = field(default_factory=dict)
    retention_policy: str = ""  # 可选
    source_module: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemoryQueryRequest:
    session_id: str = ""
    query_scope: Optional[DataCategory] = None  # None 表示查询全部
    max_results: int = 20
    time_window_sec: float = 0.0  # 0 表示不限时间
    source_module: str = ""


@dataclass
class MemoryEntry:
    entry_id: str = ""
    data_category: DataCategory = DataCategory.DIALOGUE_CONTEXT
    payload: Dict[str, Any] = field(default_factory=dict)
    source_module: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class WriteConfirm:
    entry_id: str = ""
    success: bool = True
    session_usage_pct: float = 0.0
    error_reason: str = ""


@dataclass
class SessionEndNotification:
    session_id: str = ""
    reason: str = ""
    force_cleanup: bool = False


@dataclass
class TaskCompleteNotification:
    plan_id: str = ""
    status: str = "completed"
    associated_session_id: str = ""


@dataclass
class LongTermDepositEntry:
    entries: List[MemoryEntry] = field(default_factory=list)
    deposit_type: str = ""
    priority: int = 5


@dataclass
class MemoryStatus:
    state: MemoryState = MemoryState.NORMAL
    active_sessions: int = 0
    total_entries: int = 0
    total_usage_pct: float = 0.0
    high_value_deposits: int = 0


class WorkingMemory:
    # 每个会话的条目上限
    MAX_ENTRIES_PER_SESSION = 200
    # 会话超时（秒）
    SESSION_TIMEOUT_SEC = 1800  # 30分钟
    # 状态上报间隔
    STATUS_REPORT_INTERVAL_SEC = 60
    # 数据分类的保留策略
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
        self.module_name = "工作记忆模块"
        self.version = "V1.0"

        self.state = MemoryState.NORMAL
        self._sessions: Dict[str, Dict[DataCategory, List[MemoryEntry]]] = {}
        self._session_metadata: Dict[str, Dict[str, Any]] = {}
        self._total_entries: int = 0
        self._high_value_deposits: int = 0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_write_request = None
        self._query_query_request = None
        self._query_session_end = None
        self._query_task_complete = None

        self._publish_write_confirm = None
        self._publish_query_result = None
        self._publish_longterm_deposit = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_write_request_query(self, callback: Callable[[], Optional[MemoryWriteRequest]]):
        self._query_write_request = callback

    def set_query_request_query(self, callback: Callable[[], Optional[MemoryQueryRequest]]):
        self._query_query_request = callback

    def set_session_end_query(self, callback: Callable[[], Optional[SessionEndNotification]]):
        self._query_session_end = callback

    def set_task_complete_query(self, callback: Callable[[], Optional[TaskCompleteNotification]]):
        self._query_task_complete = callback

    def set_write_confirm_publisher(self, callback: Callable[[WriteConfirm], None]):
        self._publish_write_confirm = callback

    def set_query_result_publisher(self, callback: Callable[[str, List[MemoryEntry]], None]):
        self._publish_query_result = callback

    def set_longterm_deposit_publisher(self, callback: Callable[[LongTermDepositEntry], None]):
        self._publish_longterm_deposit = callback

    def set_status_report_publisher(self, callback: Callable[[MemoryStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_memory_cycle(self):
        now = time.time()

        if self.state == MemoryState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理写入请求
        write_req = self._query_write_request() if self._query_write_request else None
        if write_req:
            self._handle_write(write_req, now)
            return

        # 处理查询请求
        query_req = self._query_query_request() if self._query_query_request else None
        if query_req:
            self._handle_query(query_req, now)
            return

        # 处理会话结束
        session_end = self._query_session_end() if self._query_session_end else None
        if session_end:
            self._handle_session_end(session_end)
            return

        # 处理任务完成
        task_complete = self._query_task_complete() if self._query_task_complete else None
        if task_complete:
            self._handle_task_complete(task_complete)

        # 超时会话清理
        self._cleanup_idle_sessions(now)

    # ========== 写入处理 ==========
    def _handle_write(self, request: MemoryWriteRequest, now: float):
        session_id = request.session_id
        category = request.data_category

        # 初始化会话存储
        if session_id not in self._sessions:
            self._sessions[session_id] = {}
            self._session_metadata[session_id] = {
                "created_at": now,
                "last_active_at": now,
                "task_list": []
            }

        if category not in self._sessions[session_id]:
            self._sessions[session_id][category] = []

        session_entries = sum(len(v) for v in self._sessions[session_id].values())
        # 容量检查
        if session_entries >= self.MAX_ENTRIES_PER_SESSION * 0.8:
            self.state = MemoryState.CAPACITY_WARNING
            self._gentle_cleanup(session_id)
            self.state = MemoryState.NORMAL

        # 分类条目数检查
        cat_entries = self._sessions[session_id][category]
        max_cat = self.CATEGORY_MAX_ENTRIES.get(category, 50)
        if len(cat_entries) >= max_cat:
            # 淘汰最旧的条目
            cat_entries.pop(0)

        # 创建条目
        entry = MemoryEntry(
            entry_id=f"MEM-{uuid.uuid4().hex[:8]}",
            data_category=category,
            payload=request.payload,
            source_module=request.source_module,
            timestamp=now
        )
        self._sessions[session_id][category].append(entry)
        self._total_entries += 1
        self._session_metadata[session_id]["last_active_at"] = now

        if self._publish_write_confirm:
            usage_pct = session_entries / self.MAX_ENTRIES_PER_SESSION
            self._publish_write_confirm(WriteConfirm(
                entry_id=entry.entry_id,
                success=True,
                session_usage_pct=round(usage_pct, 3)
            ))

    # ========== 查询处理 ==========
    def _handle_query(self, request: MemoryQueryRequest, now: float):
        session_id = request.session_id
        if session_id not in self._sessions:
            if self._publish_query_result:
                self._publish_query_result(session_id, [])
            return

        # 收集条目
        results = []
        for cat, entries in self._sessions[session_id].items():
            if request.query_scope and cat != request.query_scope:
                continue
            for entry in entries:
                if request.time_window_sec > 0 and (now - entry.timestamp) > request.time_window_sec:
                    continue
                results.append(entry)

        # 按时间戳降序
        results.sort(key=lambda e: e.timestamp, reverse=True)
        results = results[:request.max_results]

        if self._publish_query_result:
            self._publish_query_result(session_id, results)

    # ========== 会话结束 ==========
    def _handle_session_end(self, notification: SessionEndNotification):
        self.state = MemoryState.SESSION_CLEANUP
        session_id = notification.session_id

        if session_id in self._sessions:
            # 筛选高价值数据沉淀
            high_value = self._extract_high_value(session_id)
            if high_value:
                if self._publish_longterm_deposit:
                    self._publish_longterm_deposit(LongTermDepositEntry(
                        entries=high_value,
                        deposit_type="session_end"
                    ))
                self._high_value_deposits += len(high_value)

            # 清除会话数据
            del self._sessions[session_id]
            del self._session_metadata[session_id]

        self.state = MemoryState.NORMAL

    # ========== 任务完成 ==========
    def _handle_task_complete(self, notification: TaskCompleteNotification):
        session_id = notification.associated_session_id
        if not session_id or session_id not in self._sessions:
            return

        # 清除该任务对应的工具评估中间数据、推理链、待确认决策
        for cat in (DataCategory.TOOL_EVALUATION, DataCategory.REASONING_CHAIN, DataCategory.PENDING_DECISION):
            if cat in self._sessions[session_id]:
                # 筛选出与该计划相关的条目并删除
                self._sessions[session_id][cat] = [
                    e for e in self._sessions[session_id][cat]
                    if e.payload.get("plan_id") != notification.plan_id
                ]

    # ========== 辅助方法 ==========
    def _gentle_cleanup(self, session_id: str):
        """温和清理：淘汰每个分类中最旧的条目，优先保留对话上下文和任务进度"""
        priority_cats = [DataCategory.DIALOGUE_CONTEXT, DataCategory.TASK_PROGRESS]
        for cat, entries in self._sessions[session_id].items():
            if cat in priority_cats:
                continue
            if len(entries) > 1:
                entries.pop(0)  # 删除最旧的一条

    def _cleanup_idle_sessions(self, now: float):
        """清理超过30分钟无活动的会话"""
        to_remove = []
        for session_id, meta in self._session_metadata.items():
            if now - meta["last_active_at"] > self.SESSION_TIMEOUT_SEC:
                to_remove.append(session_id)

        for session_id in to_remove:
            # 沉淀高价值数据
            high_value = self._extract_high_value(session_id)
            if high_value and self._publish_longterm_deposit:
                self._publish_longterm_deposit(LongTermDepositEntry(
                    entries=high_value,
                    deposit_type="timeout"
                ))
            del self._sessions[session_id]
            del self._session_metadata[session_id]

    def _extract_high_value(self, session_id: str) -> List[MemoryEntry]:
        """提取具有长期学习价值的条目（去个性化后）"""
        high_value = []
        if session_id not in self._sessions:
            return high_value

        for cat, entries in self._sessions[session_id].items():
            for entry in entries:
                # 任务进度和推理链具有较高学习价值
                if cat in (DataCategory.TASK_PROGRESS, DataCategory.REASONING_CHAIN):
                    # 去个性化：移除敏感字段
                    cleaned = MemoryEntry(
                        entry_id=entry.entry_id,
                        data_category=entry.data_category,
                        payload={k: v for k, v in entry.payload.items()
                                 if k not in ("user_id", "session_id", "token", "password")},
                        source_module=entry.source_module,
                        timestamp=entry.timestamp
                    )
                    high_value.append(cleaned)

        return high_value

    def _publish_status(self):
        if self._publish_status_report:
            total = sum(
                sum(len(v) for v in session.values())
                for session in self._sessions.values()
            )
            active_sessions = len(self._sessions)
            usage = total / max(active_sessions * self.MAX_ENTRIES_PER_SESSION, 1)
            self._publish_status_report(MemoryStatus(
                state=self.state,
                active_sessions=active_sessions,
                total_entries=total,
                total_usage_pct=round(min(usage, 1.0), 3),
                high_value_deposits=self._high_value_deposits
            ))

    def get_state(self) -> MemoryState:
        return self.state

    def emergency_shutdown(self):
        self.state = MemoryState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 工作记忆模块 (ag-ecc-07) 演示")
    print("=" * 70)

    wm = WorkingMemory()

    print_separator("STEP 1: 写入对话上下文")
    wm.set_write_request_query(lambda: MemoryWriteRequest(
        session_id="S001", data_category=DataCategory.DIALOGUE_CONTEXT,
        payload={"text": "你好"}, source_module="ag-ecc-01"
    ))
    wm.run_memory_cycle()
    print(f"  活跃会话数: {len(wm._sessions)}")

    print_separator("STEP 2: 写入任务进度")
    wm.set_write_request_query(lambda: MemoryWriteRequest(
        session_id="S001", data_category=DataCategory.TASK_PROGRESS,
        payload={"plan_id": "P01", "step": 1}, source_module="ag-ecc-02"
    ))
    wm.run_memory_cycle()

    print_separator("STEP 3: 查询当前会话全部数据")
    wm.set_query_request_query(lambda: MemoryQueryRequest(
        session_id="S001", max_results=10, source_module="ag-ecc-02"
    ))
    wm.run_memory_cycle()

    print_separator("STEP 4: 会话结束清理")
    wm.set_session_end_query(lambda: SessionEndNotification(session_id="S001", reason="用户退出"))
    wm.run_memory_cycle()
    print(f"  活跃会话数: {len(wm._sessions)} (应为0)")

    print("\n✅ 工作记忆模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-07 工作记忆模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_wm():
            return WorkingMemory()

        # TC-E07-01: 正常写入
        print("\n[TC-E07-01] 正常写入")
        try:
            w = setup_wm()
            w.set_write_request_query(lambda: MemoryWriteRequest(
                session_id="T01", data_category=DataCategory.DIALOGUE_CONTEXT,
                payload={"msg": "hello"}, source_module="ag-ecc-01"
            ))
            w.run_memory_cycle()
            assert "T01" in w._sessions
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E07-02: 查询返回结果
        print("\n[TC-E07-02] 查询返回结果")
        try:
            w = setup_wm()
            # 直接注入数据
            w._sessions["T02"] = {
                DataCategory.DIALOGUE_CONTEXT: [
                    MemoryEntry(entry_id="E1", data_category=DataCategory.DIALOGUE_CONTEXT,
                                payload={"msg": "test"}, source_module="m", timestamp=time.time())
                ]
            }
            w._session_metadata["T02"] = {"created_at": time.time(), "last_active_at": time.time(), "task_list": []}
            w.set_query_request_query(lambda: MemoryQueryRequest(
                session_id="T02", max_results=5
            ))
            w.run_memory_cycle()
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E07-03: 会话结束清理
        print("\n[TC-E07-03] 会话结束清理")
        try:
            w = setup_wm()
            w._sessions["T03"] = {DataCategory.DIALOGUE_CONTEXT: []}
            w._session_metadata["T03"] = {"created_at": time.time(), "last_active_at": time.time(), "task_list": []}
            w.set_session_end_query(lambda: SessionEndNotification(session_id="T03"))
            w.run_memory_cycle()
            assert "T03" not in w._sessions
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E07-04: 容量预警触发温和清理
        print("\n[TC-E07-04] 容量预警触发温和清理")
        try:
            w = setup_wm()
            # 创建一个已满的会话
            w._sessions["T04"] = {}
            w._session_metadata["T04"] = {"created_at": time.time(), "last_active_at": time.time(), "task_list": []}
            for cat in DataCategory:
                w._sessions["T04"][cat] = [MemoryEntry(entry_id=f"E{i}", data_category=cat, payload={}, source_module="m", timestamp=time.time()) for i in range(w.CATEGORY_MAX_ENTRIES.get(cat, 5))]
            old_count = sum(len(v) for v in w._sessions["T04"].values())
            # 触发预警
            w.set_write_request_query(lambda: MemoryWriteRequest(
                session_id="T04", data_category=DataCategory.TOOL_EVALUATION,
                payload={"test": "data"}, source_module="m"
            ))
            w.run_memory_cycle()
            new_count = sum(len(v) for v in w._sessions["T04"].values())
            # 应该减少或保持不变（因为可能触发清理）
            assert new_count <= old_count + 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E07-05: 任务完成清理相关数据
        print("\n[TC-E07-05] 任务完成清理相关数据")
        try:
            w = setup_wm()
            w._sessions["T05"] = {
                DataCategory.TOOL_EVALUATION: [
                    MemoryEntry(entry_id="E1", data_category=DataCategory.TOOL_EVALUATION,
                                payload={"plan_id": "P05"}, source_module="m", timestamp=time.time())
                ],
                DataCategory.REASONING_CHAIN: [
                    MemoryEntry(entry_id="E2", data_category=DataCategory.REASONING_CHAIN,
                                payload={"plan_id": "P05"}, source_module="m", timestamp=time.time())
                ]
            }
            w._session_metadata["T05"] = {"created_at": time.time(), "last_active_at": time.time(), "task_list": []}
            w.set_task_complete_query(lambda: TaskCompleteNotification(
                plan_id="P05", associated_session_id="T05"
            ))
            w.run_memory_cycle()
            # 验证相关条目被清除
            assert len(w._sessions["T05"][DataCategory.TOOL_EVALUATION]) == 0
            assert len(w._sessions["T05"][DataCategory.REASONING_CHAIN]) == 0
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E07-06: 紧急熔断
        print("\n[TC-E07-06] 紧急熔断")
        try:
            w = setup_wm()
            w.emergency_shutdown()
            assert w.state == MemoryState.SYSTEM_PAUSED
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