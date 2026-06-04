#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-12
模块名称: 资源调度模块
所属分区: 一、认知大脑核心模块
核心职责: 作为 ECC 认知大脑的全局中枢与唯一对外网关，统筹管理系统的算力、内存、存储、
          网络带宽及大模型 API 调用配额等关键资源。负责跨系统通信的统一代理——所有 ECC
          模块与记忆中枢（MLNF-Mem）的 MemoryBus 通信、与运动小脑（MCC）的 CerebellumBus
          通信、与外部大模型服务的 API 调用，均需通过本模块中转与安全校验。同时承担系统
          熔断保护、人机主权闭锁、权限管控、全链路审计与资源调度日志的归档。不参与任何
          认知决策，仅执行资源分配、通信代理与安全策略的执行。

依赖模块:
    ag-ecc-01~11(全部ECC模块), ag-mem-01(总控漏斗F₀), ag-mcc-01(执行调度核心),
    外部大模型API服务
被依赖模块:
    ag-ecc-01~11(全部ECC模块)

安全约束:
  R-01: 本模块为 ECC 认知大脑的唯一对外网关，所有跨系统通信必须经本模块中转
  R-02: 安全仲裁模块下发的熔断/降级/闭锁指令具有最高优先级，本模块必须无条件执行
  R-03: 外部大模型调用必须经过配额管理，单日调用量不得超过预设限额
  R-04: 所有跨系统通信必须记录完整的审计日志
  R-05: 主权闭锁状态一旦触发，仅可人工解除，任何自动化模块无权恢复自动化操作
  R-06: 系统资源监控数据仅用于内部调度决策，不得泄露给外部系统
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class SchedulerState(Enum):
    NORMAL_SCHEDULING = "normal_scheduling"
    RESOURCE_WARNING = "resource_warning"
    RESOURCE_CRITICAL = "resource_critical"
    CIRCUIT_BREAKER = "circuit_breaker"
    HUMAN_LOCKDOWN = "human_lockdown"
    SYSTEM_PAUSED = "system_paused"


class TargetSystem(Enum):
    MLNF_MEM = "MLNF-Mem"
    MCC = "MCC"
    LLM = "大模型"


class DegradeLevel(Enum):
    LEVEL_1 = "一级降级"
    LEVEL_2 = "二级降级"
    LEVEL_3 = "三级降级"


@dataclass
class ResourceQueryRequest:
    requester_module: str = ""
    query_type: str = ""
    description: str = ""


@dataclass
class CrossSystemRequest:
    request_id: str = ""
    requester_module: str = ""
    target_system: TargetSystem = TargetSystem.MLNF_MEM
    message_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    timestamp: float = field(default_factory=time.time)


@dataclass
class AnomalyAlert:
    source_module: str = ""
    alert_type: str = ""
    severity: str = ""
    details: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SafetyDegradeCommand:
    command_type: str = ""
    target_level: int = 1
    reason: str = ""
    affected_modules: List[str] = field(default_factory=list)


@dataclass
class HumanLockdownSignal:
    reason: str = ""
    source: str = ""
    force_execution: bool = False


@dataclass
class SystemResourceData:
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0
    storage_usage_pct: float = 0.0
    network_bandwidth_pct: float = 0.0
    active_connections: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResourceAllocationResult:
    requester_module: str = ""
    allocation_type: str = ""
    allocated_amount: float = 0.0
    valid_until_sec: float = 300.0
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceWarningNotice:
    warning_type: str = ""
    current_usage_pct: float = 0.0
    threshold: float = 0.0
    affected_modules: List[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class DegradeCommand:
    target_modules: List[str] = field(default_factory=list)
    degrade_level: DegradeLevel = DegradeLevel.LEVEL_1
    measures: str = ""
    estimated_duration_sec: float = 0.0


@dataclass
class CircuitBreakerBroadcast:
    breaker_level: int = 1
    reason: str = ""
    affected_scope: str = "全系统"
    recovery_condition: str = ""


@dataclass
class HumanLockdownConfirm:
    lockdown_state: bool = True
    suspended_automation: List[str] = field(default_factory=list)
    human_takeover_entry: str = "管理控制台"


@dataclass
class AuditLog:
    event_type: str = ""
    involved_module: str = ""
    communication_summary: str = ""
    resource_consumption: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class SchedulerStatus:
    state: SchedulerState = SchedulerState.NORMAL_SCHEDULING
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0
    storage_usage_pct: float = 0.0
    active_connections: int = 0
    today_communication_count: int = 0
    alert_count: int = 0


class ResourceScheduler:
    # 资源阈值
    CPU_WARN_THRESHOLD = 80.0
    CPU_CRITICAL_THRESHOLD = 95.0
    MEMORY_WARN_THRESHOLD = 80.0
    MEMORY_CRITICAL_THRESHOLD = 95.0
    STORAGE_WARN_THRESHOLD = 80.0
    STORAGE_CRITICAL_THRESHOLD = 95.0

    # 大模型配额
    LLM_DAILY_QUOTA = 100000  # Token
    LLM_QUOTA_WARN_RATIO = 0.80
    LLM_QUOTA_CRITICAL_RATIO = 0.95

    # 通信队列
    MAX_QUEUE_SIZE = 1000
    STATUS_REPORT_INTERVAL_SEC = 30

    # 记忆中枢写入限制（二级降级时启用）
    MEM_WRITE_LIMIT_ENABLED = False
    MEM_WRITE_LIMIT_PER_SEC = 10

    def __init__(self):
        self.module_id = "ag-ecc-12"
        self.module_name = "资源调度模块"
        self.version = "V1.0"

        self.state = SchedulerState.NORMAL_SCHEDULING
        self._resource_cache: Dict[str, float] = {}
        self._communication_queue: List[CrossSystemRequest] = []
        self._llm_token_used_today: int = 0
        self._llm_quota_warning_sent: bool = False
        self._today_communication_count: int = 0
        self._alert_count: int = 0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_resource_query = None
        self._query_cross_system_request = None
        self._query_anomaly_alert = None
        self._query_safety_degrade = None
        self._query_human_lockdown = None
        self._query_system_resource = None

        self._publish_resource_result = None
        self._publish_memory_bus_forward = None
        self._publish_cerebellum_bus_command = None
        self._publish_llm_api_request = None
        self._publish_warning_notice = None
        self._publish_degrade_command = None
        self._publish_circuit_breaker = None
        self._publish_lockdown_confirm = None
        self._publish_audit_log = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_resource_query_query(self, callback: Callable[[], Optional[ResourceQueryRequest]]):
        self._query_resource_query = callback

    def set_cross_system_request_query(self, callback: Callable[[], Optional[CrossSystemRequest]]):
        self._query_cross_system_request = callback

    def set_anomaly_alert_query(self, callback: Callable[[], Optional[AnomalyAlert]]):
        self._query_anomaly_alert = callback

    def set_safety_degrade_query(self, callback: Callable[[], Optional[SafetyDegradeCommand]]):
        self._query_safety_degrade = callback

    def set_human_lockdown_query(self, callback: Callable[[], Optional[HumanLockdownSignal]]):
        self._query_human_lockdown = callback

    def set_system_resource_query(self, callback: Callable[[], Optional[SystemResourceData]]):
        self._query_system_resource = callback

    def set_resource_result_publisher(self, callback: Callable[[ResourceAllocationResult], None]):
        self._publish_resource_result = callback

    def set_memory_bus_forward_publisher(self, callback: Callable[[CrossSystemRequest], None]):
        self._publish_memory_bus_forward = callback

    def set_cerebellum_bus_command_publisher(self, callback: Callable[[CrossSystemRequest], None]):
        self._publish_cerebellum_bus_command = callback

    def set_llm_api_request_publisher(self, callback: Callable[[CrossSystemRequest], None]):
        self._publish_llm_api_request = callback

    def set_warning_notice_publisher(self, callback: Callable[[ResourceWarningNotice], None]):
        self._publish_warning_notice = callback

    def set_degrade_command_publisher(self, callback: Callable[[DegradeCommand], None]):
        self._publish_degrade_command = callback

    def set_circuit_breaker_publisher(self, callback: Callable[[CircuitBreakerBroadcast], None]):
        self._publish_circuit_breaker = callback

    def set_lockdown_confirm_publisher(self, callback: Callable[[HumanLockdownConfirm], None]):
        self._publish_lockdown_confirm = callback

    def set_audit_log_publisher(self, callback: Callable[[AuditLog], None]):
        self._publish_audit_log = callback

    def set_status_report_publisher(self, callback: Callable[[SchedulerStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_scheduler_cycle(self):
        now = time.time()

        if self.state == SchedulerState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理最高优先级的安全指令
        safety_degrade = self._query_safety_degrade() if self._query_safety_degrade else None
        if safety_degrade:
            self._handle_safety_degrade(safety_degrade)
            return

        human_lockdown = self._query_human_lockdown() if self._query_human_lockdown else None
        if human_lockdown:
            self._handle_human_lockdown(human_lockdown)
            return

        # 资源监控
        sys_resource = self._query_system_resource() if self._query_system_resource else None
        if sys_resource:
            self._monitor_resources(sys_resource)

        # 处理跨系统通信请求
        cross_req = self._query_cross_system_request() if self._query_cross_system_request else None
        if cross_req:
            self._handle_cross_system_request(cross_req)
            return

        # 处理资源查询请求
        resource_req = self._query_resource_query() if self._query_resource_query else None
        if resource_req:
            self._handle_resource_query(resource_req)

    # ========== 资源监控 ==========
    def _monitor_resources(self, resource: SystemResourceData):
        # 更新缓存
        self._resource_cache = {
            "cpu": resource.cpu_usage_pct,
            "memory": resource.memory_usage_pct,
            "storage": resource.storage_usage_pct,
        }

        # 紧急状态判定
        if (resource.cpu_usage_pct >= self.CPU_CRITICAL_THRESHOLD or
            resource.memory_usage_pct >= self.MEMORY_CRITICAL_THRESHOLD or
            resource.storage_usage_pct >= self.STORAGE_CRITICAL_THRESHOLD):
            if self.state != SchedulerState.RESOURCE_CRITICAL:
                self.state = SchedulerState.RESOURCE_CRITICAL
                self._trigger_degrade(DegradeLevel.LEVEL_3)
                self._broadcast_warning("紧急", resource)

        # 预警状态判定
        elif (resource.cpu_usage_pct >= self.CPU_WARN_THRESHOLD or
              resource.memory_usage_pct >= self.MEMORY_WARN_THRESHOLD or
              resource.storage_usage_pct >= self.STORAGE_WARN_THRESHOLD):
            if self.state == SchedulerState.NORMAL_SCHEDULING:
                self.state = SchedulerState.RESOURCE_WARNING
                self._trigger_degrade(DegradeLevel.LEVEL_1)
                self._broadcast_warning("预警", resource)

        else:
            if self.state in (SchedulerState.RESOURCE_WARNING, SchedulerState.RESOURCE_CRITICAL):
                self.state = SchedulerState.NORMAL_SCHEDULING
                # 恢复正常后重置降级标记
                self.MEM_WRITE_LIMIT_ENABLED = False

    def _trigger_degrade(self, level: DegradeLevel):
        if level == DegradeLevel.LEVEL_1:
            if self._publish_degrade_command:
                self._publish_degrade_command(DegradeCommand(
                    target_modules=[],
                    degrade_level=level,
                    measures="暂停非关键后台任务，延长轮询间隔至500ms"
                ))
        elif level == DegradeLevel.LEVEL_2:
            # 修复：实现二级降级措施
            self.MEM_WRITE_LIMIT_ENABLED = True
            if self._publish_degrade_command:
                self._publish_degrade_command(DegradeCommand(
                    target_modules=[],
                    degrade_level=level,
                    measures="暂停大模型调用，限制记忆中枢写入频率"
                ))
        elif level == DegradeLevel.LEVEL_3:
            if self._publish_degrade_command:
                self._publish_degrade_command(DegradeCommand(
                    target_modules=[],
                    degrade_level=level,
                    measures="仅保留安全模块与基本通信，暂停一切非必要服务"
                ))

    def _broadcast_warning(self, level: str, resource: SystemResourceData):
        if self._publish_warning_notice:
            self._publish_warning_notice(ResourceWarningNotice(
                warning_type=level,
                current_usage_pct=max(resource.cpu_usage_pct, resource.memory_usage_pct, resource.storage_usage_pct),
                threshold=self.CPU_CRITICAL_THRESHOLD if level == "紧急" else self.CPU_WARN_THRESHOLD,
                affected_modules=["全部"],
                suggested_action="触发降级" if level == "紧急" else "关注资源使用"
            ))
        self._alert_count += 1

    # ========== 安全指令处理 ==========
    def _handle_safety_degrade(self, command: SafetyDegradeCommand):
        if command.command_type == "circuit_breaker":
            self.state = SchedulerState.CIRCUIT_BREAKER
            self._communication_queue.clear()
            if self._publish_circuit_breaker:
                self._publish_circuit_breaker(CircuitBreakerBroadcast(
                    breaker_level=command.target_level,
                    reason=command.reason,
                    affected_scope="全系统",
                    recovery_condition="安全态势恢复正常"
                ))

    def _handle_human_lockdown(self, signal: HumanLockdownSignal):
        self.state = SchedulerState.HUMAN_LOCKDOWN
        self._communication_queue.clear()
        if self._publish_lockdown_confirm:
            self._publish_lockdown_confirm(HumanLockdownConfirm(
                lockdown_state=True,
                suspended_automation=["全部自动化决策"],
                human_takeover_entry="管理控制台"
            ))

    # ========== 跨系统通信 ==========
    def _handle_cross_system_request(self, request: CrossSystemRequest):
        # 熔断/闭锁状态下拒绝非安全通信
        if self.state in (SchedulerState.CIRCUIT_BREAKER, SchedulerState.HUMAN_LOCKDOWN):
            if request.message_type not in ("安全指令", "熔断确认"):
                self._log_event("COMMUNICATION_REJECTED", {
                    "reason": "系统处于熔断/闭锁状态",
                    "requester": request.requester_module
                })
                return

        # 按目标系统路由
        if request.target_system == TargetSystem.MLNF_MEM:
            # 二级降级时限制记忆中枢写入频率
            if self.MEM_WRITE_LIMIT_ENABLED and "写入" in request.message_type:
                self._log_event("MEM_WRITE_LIMITED", {
                    "requester": request.requester_module,
                    "message_type": request.message_type
                })
                return
            if self._publish_memory_bus_forward:
                self._publish_memory_bus_forward(request)
        elif request.target_system == TargetSystem.MCC:
            if self._publish_cerebellum_bus_command:
                self._publish_cerebellum_bus_command(request)
        elif request.target_system == TargetSystem.LLM:
            self._handle_llm_request(request)

        # 记录审计日志
        self._today_communication_count += 1
        if self._publish_audit_log:
            self._publish_audit_log(AuditLog(
                event_type="跨系统通信",
                involved_module=request.requester_module,
                communication_summary=f"{request.message_type} -> {request.target_system.value}",
                resource_consumption=0.0
            ))

    def _handle_llm_request(self, request: CrossSystemRequest):
        # 修复：配额预警检查
        warn_threshold = int(self.LLM_DAILY_QUOTA * self.LLM_QUOTA_WARN_RATIO)
        critical_threshold = int(self.LLM_DAILY_QUOTA * self.LLM_QUOTA_CRITICAL_RATIO)

        # 配额预警通知（80%）
        if self._llm_token_used_today >= warn_threshold and not self._llm_quota_warning_sent:
            self._llm_quota_warning_sent = True
            self._log_event("LLM_QUOTA_WARNING", {
                "used_tokens": self._llm_token_used_today,
                "daily_quota": self.LLM_DAILY_QUOTA,
                "usage_pct": round(self._llm_token_used_today / self.LLM_DAILY_QUOTA * 100, 1)
            })

        # 配额耗尽拒绝（95%）
        if self._llm_token_used_today >= critical_threshold:
            self._log_event("LLM_QUOTA_EXHAUSTED", {"used": self._llm_token_used_today})
            return

        # 估算Token消耗
        estimated_tokens = len(str(request.payload)) // 4
        self._llm_token_used_today += estimated_tokens

        if self._publish_llm_api_request:
            self._publish_llm_api_request(request)

    # ========== 资源查询 ==========
    def _handle_resource_query(self, request: ResourceQueryRequest):
        result = ResourceAllocationResult(
            requester_module=request.requester_module,
            allocation_type=request.query_type,
            allocated_amount=100.0,
            valid_until_sec=300.0,
            constraints={"max_concurrent": 5}
        )
        if self._publish_resource_result:
            self._publish_resource_result(result)

    # ========== 辅助 ==========
    def _publish_status(self):
        if self._publish_status_report:
            self._publish_status_report(SchedulerStatus(
                state=self.state,
                cpu_usage_pct=self._resource_cache.get("cpu", 0.0),
                memory_usage_pct=self._resource_cache.get("memory", 0.0),
                storage_usage_pct=self._resource_cache.get("storage", 0.0),
                active_connections=0,
                today_communication_count=self._today_communication_count,
                alert_count=self._alert_count
            ))

    def get_state(self) -> SchedulerState:
        return self.state

    def emergency_shutdown(self):
        self.state = SchedulerState.SYSTEM_PAUSED
        self._communication_queue.clear()
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
    print("  Agent-ecc-brain 资源调度模块 (ag-ecc-12) 演示")
    print("=" * 70)

    scheduler = ResourceScheduler()

    print_separator("STEP 1: 正常调度状态")
    scheduler.set_system_resource_query(lambda: SystemResourceData(
        cpu_usage_pct=45.0, memory_usage_pct=60.0, storage_usage_pct=30.0
    ))
    scheduler.run_scheduler_cycle()
    print(f"  状态: {scheduler.state.value}")

    print_separator("STEP 2: 资源预警触发一级降级")
    scheduler.set_system_resource_query(lambda: SystemResourceData(
        cpu_usage_pct=82.0, memory_usage_pct=75.0, storage_usage_pct=40.0
    ))
    scheduler.run_scheduler_cycle()
    print(f"  状态: {scheduler.state.value}")

    print_separator("STEP 3: 大模型配额预警")
    scheduler._llm_token_used_today = 85000  # 超过80%
    scheduler.set_cross_system_request_query(lambda: CrossSystemRequest(
        request_id="REQ-LLM", requester_module="ag-ecc-08",
        target_system=TargetSystem.LLM, message_type="大模型调用",
        payload={"prompt": "test" * 100}
    ))
    scheduler.run_scheduler_cycle()
    print(f"  Token用量: {scheduler._llm_token_used_today}")
    print(f"  配额预警已发送: {scheduler._llm_quota_warning_sent}")

    print_separator("STEP 4: 二级降级（限制记忆中枢写入）")
    scheduler._trigger_degrade(DegradeLevel.LEVEL_2)
    scheduler.set_cross_system_request_query(lambda: CrossSystemRequest(
        request_id="REQ-MEM-W", requester_module="ag-ecc-06",
        target_system=TargetSystem.MLNF_MEM, message_type="经验写入",
        payload={"entry": "test"}
    ))
    scheduler.run_scheduler_cycle()
    print(f"  写入限制启用: {scheduler.MEM_WRITE_LIMIT_ENABLED}")

    print("\n✅ 资源调度模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-12 资源调度模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_scheduler():
            return ResourceScheduler()

        # TC-E12-01: 正常转发MLNF-Mem请求
        print("\n[TC-E12-01] 正常转发MLNF-Mem请求")
        try:
            s = setup_scheduler()
            s.set_cross_system_request_query(lambda: CrossSystemRequest(
                request_id="T01", requester_module="ag-ecc-05",
                target_system=TargetSystem.MLNF_MEM, message_type="经验查询"
            ))
            s.run_scheduler_cycle()
            assert s._today_communication_count == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E12-02: 资源预警切换状态
        print("\n[TC-E12-02] 资源预警切换状态")
        try:
            s = setup_scheduler()
            s.set_system_resource_query(lambda: SystemResourceData(
                cpu_usage_pct=82.0, memory_usage_pct=75.0, storage_usage_pct=40.0
            ))
            s.run_scheduler_cycle()
            assert s.state == SchedulerState.RESOURCE_WARNING
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E12-03: 熔断指令执行
        print("\n[TC-E12-03] 熔断指令执行")
        try:
            s = setup_scheduler()
            s.set_safety_degrade_query(lambda: SafetyDegradeCommand(
                command_type="circuit_breaker", target_level=3, reason="测试"
            ))
            s.run_scheduler_cycle()
            assert s.state == SchedulerState.CIRCUIT_BREAKER
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E12-04: 熔断状态拒绝非安全通信
        print("\n[TC-E12-04] 熔断状态拒绝非安全通信")
        try:
            s = setup_scheduler()
            s.state = SchedulerState.CIRCUIT_BREAKER
            s.set_cross_system_request_query(lambda: CrossSystemRequest(
                request_id="T04", requester_module="ag-ecc-03",
                target_system=TargetSystem.LLM, message_type="普通请求"
            ))
            s.run_scheduler_cycle()
            assert s._today_communication_count == 0
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E12-05: 二级降级限制记忆中枢写入
        print("\n[TC-E12-05] 二级降级限制记忆中枢写入")
        try:
            s = setup_scheduler()
            s._trigger_degrade(DegradeLevel.LEVEL_2)
            assert s.MEM_WRITE_LIMIT_ENABLED
            s.set_cross_system_request_query(lambda: CrossSystemRequest(
                request_id="T05", requester_module="ag-ecc-06",
                target_system=TargetSystem.MLNF_MEM, message_type="经验写入"
            ))
            s.run_scheduler_cycle()
            assert s._today_communication_count == 0  # 被限制，未计数
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E12-06: 紧急熔断
        print("\n[TC-E12-06] 紧急熔断")
        try:
            s = setup_scheduler()
            s.emergency_shutdown()
            assert s.state == SchedulerState.SYSTEM_PAUSED
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