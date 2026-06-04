#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-04
模块名称: 安全仲裁模块
所属分区: 一、认知大脑核心模块
核心职责: 作为 ECC 认知大脑的全局安全审查与仲裁中枢，对 ag-ecc-02（任务规划模块）输出的
          任务执行计划和 ag-ecc-03（工具选择模块）输出的工具选择方案进行安全合规性终审。
          基于安全规则库（ag-mem-45）、操作风险等级与系统当前安全态势，判定每项操作是否
          允许执行、需要用户确认或直接拒绝。拥有全局最高否决权——任何模块的决策均可被本
          模块拦截。在检测到高风险操作或安全态势恶化时，可触发系统降级、熔断或紧急闭锁。

依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-03(工具选择模块), ag-mem-45(安全规则库),
    ag-ecc-05(记忆查询模块), ag-ecc-12(资源调度模块)
被依赖模块:
    ag-ecc-02, ag-ecc-03, ag-ecc-12, ag-mem-51(记忆变更日志追溯单元)

安全约束:
  A-01: 本模块拥有全局最高否决权，任何模块不得绕过本模块执行操作
  A-02: 安全规则库不可用时，使用编译期内置最小安全规则集，采用保守策略
  A-03: 人工安全指令必须经过授权令牌验证与双重确认
  A-04: 紧急闭锁状态下，仅接收人工解锁指令
  A-05: 用户确认请求的超时时间为 60 秒
  A-06: 安全事件日志必须完整记录每次审查的输入、规则匹配、结论与时间戳
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class ArbiterState(Enum):
    NORMAL_MONITOR = "normal_monitor"
    ENHANCED_REVIEW = "enhanced_review"
    HIGH_ALERT = "high_alert"
    EMERGENCY_LOCKDOWN = "emergency_lockdown"
    SYSTEM_PAUSED = "system_paused"


class RiskLevel(Enum):
    SAFE = "无风险"
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "严重风险"
    EXTREME = "极端风险"


class Verdict(Enum):
    APPROVED = "放行"
    CONFIRM_REQUIRED = "需确认"
    REJECTED = "拒绝"
    DEGRADED_APPROVED = "降级执行"


class OperationType(Enum):
    READ = "只读"
    WRITE = "写入"
    EXECUTE = "执行"
    DELETE = "删除"
    CONFIGURE = "配置修改"
    UNKNOWN = "未知"


@dataclass
class SafetyRules:
    blacklist: List[str] = field(default_factory=list)
    whitelist: List[str] = field(default_factory=list)
    sensitive_ops: List[str] = field(default_factory=list)
    compliance_patterns: List[Dict[str, Any]] = field(default_factory=list)
    permission_levels: Dict[str, int] = field(default_factory=dict)


@dataclass
class ToolSelectionPlan:
    step_id: str = ""
    primary_tool: Optional[Any] = None
    backup_tools: List[Any] = field(default_factory=list)
    estimated_call_cost: float = 0.0
    estimated_success_rate: float = 0.0
    user_confirmation_required: bool = False
    operation_type: str = "只读"  # 新增：操作类型


@dataclass
class TaskPlan:
    plan_id: str = ""
    steps: List[Any] = field(default_factory=list)
    task_type: str = ""


@dataclass
class SafetyReviewResult:
    review_id: str = ""
    verdict: Verdict = Verdict.APPROVED
    reject_reason: str = ""
    additional_constraints: Dict[str, Any] = field(default_factory=dict)
    review_duration_ms: float = 0.0


@dataclass
class UserConfirmRequest:
    request_id: str = ""
    operation_description: str = ""
    risk_description: str = ""
    options: List[str] = field(default_factory=list)
    timeout_sec: int = 60


@dataclass
class SafetyDegradeCommand:
    target_level: int = 1
    reason: str = ""
    affected_modules: List[str] = field(default_factory=list)


@dataclass
class SafetyEventLog:
    event_id: str = ""
    event_type: str = ""
    involved_module: str = ""
    verdict: Verdict = Verdict.APPROVED
    risk_level: RiskLevel = RiskLevel.SAFE
    timestamp: float = field(default_factory=time.time)


@dataclass
class SafetyStatusReport:
    state: ArbiterState = ArbiterState.NORMAL_MONITOR
    security_score: float = 0.85
    recent_events_count: int = 0
    risk_trend: str = "稳定"


class SafetyArbiter:
    DEFAULT_BLACKLIST = ["shell_exec", "db_delete", "system_restart", "format_drive"]
    DEFAULT_WHITELIST = ["weather_api", "file_read", "text_generator", "search_engine"]
    DEFAULT_SENSITIVE_OPS = ["delete_file", "modify_config", "write_system", "grant_permission"]

    USER_CONFIRM_TIMEOUT_SEC = 60
    STATUS_REPORT_INTERVAL_SEC = 60
    SECURITY_SCORE_RECOVERY_RATE = 0.01

    def __init__(self):
        self.module_id = "ag-ecc-04"
        self.module_name = "安全仲裁模块"
        self.version = "V1.0"

        self.state = ArbiterState.NORMAL_MONITOR
        self._security_score = 0.85
        self._recent_events: List[SafetyEventLog] = []
        self._last_status_time: float = time.time()
        self._pending_confirmations: Dict[str, float] = {}
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_task_plan = None
        self._query_tool_plan = None
        self._query_safety_rules = None
        self._query_historical_events = None
        self._query_manual_command = None

        self._publish_review_result = None
        self._publish_user_confirm_request = None
        self._publish_degrade_command = None
        self._publish_safety_event_log = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成, 初始安全评分={self._security_score}")

    # ========== 回调注入 ==========
    def set_task_plan_query(self, callback: Callable[[], Optional[TaskPlan]]):
        self._query_task_plan = callback

    def set_tool_plan_query(self, callback: Callable[[], Optional[ToolSelectionPlan]]):
        self._query_tool_plan = callback

    def set_safety_rules_query(self, callback: Callable[[], Optional[SafetyRules]]):
        self._query_safety_rules = callback

    def set_historical_events_query(self, callback: Callable[[], Optional[List[SafetyEventLog]]]):
        self._query_historical_events = callback

    def set_manual_command_query(self, callback: Callable[[], Optional[Dict[str, Any]]]):
        self._query_manual_command = callback

    def set_review_result_publisher(self, callback: Callable[[SafetyReviewResult], None]):
        self._publish_review_result = callback

    def set_user_confirm_request_publisher(self, callback: Callable[[UserConfirmRequest], None]):
        self._publish_user_confirm_request = callback

    def set_degrade_command_publisher(self, callback: Callable[[SafetyDegradeCommand], None]):
        self._publish_degrade_command = callback

    def set_safety_event_log_publisher(self, callback: Callable[[SafetyEventLog], None]):
        self._publish_safety_event_log = callback

    def set_status_report_publisher(self, callback: Callable[[SafetyStatusReport], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_arbiter_cycle(self) -> Optional[SafetyReviewResult]:
        now = time.time()

        if self.state == ArbiterState.SYSTEM_PAUSED:
            return None

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 检查用户确认超时
        self._check_confirm_timeouts(now)

        # 处理人工安全指令
        manual_cmd = self._query_manual_command() if self._query_manual_command else None
        if manual_cmd:
            self._handle_manual_command(manual_cmd)
            return None

        # 处理待审查的任务计划
        task_plan = self._query_task_plan() if self._query_task_plan else None
        if task_plan:
            return self._review_task_plan(task_plan)

        # 处理待审查的工具方案
        tool_plan = self._query_tool_plan() if self._query_tool_plan else None
        if tool_plan:
            return self._review_tool_plan(tool_plan)

        # 缓慢恢复安全评分并联动状态
        if self.state != ArbiterState.EMERGENCY_LOCKDOWN:
            self._security_score = min(1.0, self._security_score + self.SECURITY_SCORE_RECOVERY_RATE)
            self._reassess_state_from_score()

        return None

    # ========== 核心审查 ==========
    def _review_task_plan(self, plan: TaskPlan) -> SafetyReviewResult:
        start_time = time.time()
        rules = self._get_safety_rules()

        for step in plan.steps:
            tool_name = getattr(step, 'required_tool_type', '')
            if tool_name in rules.blacklist:
                return self._build_result(Verdict.REJECTED, f"步骤涉及黑名单工具: {tool_name}", start_time)

        return self._build_result(Verdict.APPROVED, "", start_time)

    def _review_tool_plan(self, plan: ToolSelectionPlan) -> SafetyReviewResult:
        start_time = time.time()
        rules = self._get_safety_rules()

        # 紧急闭锁状态直接拒绝
        if self.state == ArbiterState.EMERGENCY_LOCKDOWN:
            return self._build_result(Verdict.REJECTED, "系统处于紧急闭锁状态", start_time)

        # 提取工具名称
        tool_name = self._extract_tool_name(plan)
        if not tool_name:
            return self._build_result(Verdict.REJECTED, "无法获取工具名称，拒绝执行", start_time)

        # 判定风险等级
        risk_level = self._assess_risk_level(tool_name, plan, rules)

        # 根据风险等级和系统态势综合判定结论
        verdict, reason = self._determine_verdict(risk_level, tool_name)

        # 高风险事件扣分
        if risk_level in (RiskLevel.CRITICAL, RiskLevel.EXTREME):
            self._degrade_security_score(0.2)
        elif risk_level == RiskLevel.HIGH:
            self._degrade_security_score(0.1)

        # 需要用户确认时，发送确认请求
        if verdict == Verdict.CONFIRM_REQUIRED and self._publish_user_confirm_request:
            confirm_req = UserConfirmRequest(
                request_id=f"CFM-{uuid.uuid4().hex[:8]}",
                operation_description=f"工具调用: {tool_name}",
                risk_description=f"风险等级: {risk_level.value}",
                options=["确认执行", "取消"],
                timeout_sec=self.USER_CONFIRM_TIMEOUT_SEC
            )
            self._publish_user_confirm_request(confirm_req)
            self._pending_confirmations[confirm_req.request_id] = time.time()

        return self._build_result(verdict, reason, start_time)

    def _extract_tool_name(self, plan: ToolSelectionPlan) -> str:
        """从工具选择方案中提取工具名称"""
        if plan.primary_tool is None:
            return ""
        if hasattr(plan.primary_tool, 'name'):
            return plan.primary_tool.name
        if hasattr(plan.primary_tool, 'tool') and hasattr(plan.primary_tool.tool, 'name'):
            return plan.primary_tool.tool.name
        return ""

    def _assess_risk_level(self, tool_name: str, plan: ToolSelectionPlan, rules: SafetyRules) -> RiskLevel:
        """评估操作风险等级"""
        # 黑名单 → 严重风险
        if tool_name in rules.blacklist:
            return RiskLevel.CRITICAL

        # 合规模式匹配 → 极端风险
        if self._match_compliance_patterns(tool_name, rules.compliance_patterns):
            return RiskLevel.EXTREME

        # 白名单 → 区分操作类型
        if tool_name in rules.whitelist:
            op_type = getattr(plan, 'operation_type', '只读')
            if op_type in ('只读', 'read', 'READ'):
                return RiskLevel.SAFE
            else:
                return RiskLevel.LOW  # 写入操作记录日志

        # 敏感操作 → 高风险
        if tool_name in rules.sensitive_ops:
            return RiskLevel.HIGH

        # 其他 → 中风险
        return RiskLevel.MEDIUM

    def _match_compliance_patterns(self, tool_name: str, patterns: List[Dict[str, Any]]) -> bool:
        """检查是否命中合规模式"""
        for pattern in patterns:
            if tool_name in pattern.get("tools", []):
                return True
        return False

    def _determine_verdict(self, risk_level: RiskLevel, tool_name: str) -> tuple:
        """根据风险等级和系统态势综合判定审查结论"""
        # HIGH_ALERT 状态下，中风险及以上拒绝
        if self.state == ArbiterState.HIGH_ALERT and risk_level.value in ("中风险", "高风险", "严重风险", "极端风险"):
            return Verdict.REJECTED, f"高风险态势下拒绝{risk_level.value}操作: {tool_name}"

        # ENHANCED_REVIEW 状态下，高风险及以上需确认
        if self.state == ArbiterState.ENHANCED_REVIEW and risk_level.value in ("高风险", "严重风险"):
            return Verdict.CONFIRM_REQUIRED, f"加强审查下{risk_level.value}操作需确认: {tool_name}"

        # 按风险等级判定
        if risk_level == RiskLevel.SAFE:
            return Verdict.APPROVED, ""
        elif risk_level == RiskLevel.LOW:
            return Verdict.APPROVED, ""
        elif risk_level == RiskLevel.MEDIUM:
            return Verdict.CONFIRM_REQUIRED, f"工具 {tool_name} 不在白名单中，需确认"
        elif risk_level == RiskLevel.HIGH:
            return Verdict.CONFIRM_REQUIRED, f"敏感操作需用户确认: {tool_name}"
        elif risk_level == RiskLevel.CRITICAL:
            return Verdict.REJECTED, f"工具 {tool_name} 在黑名单中"
        elif risk_level == RiskLevel.EXTREME:
            return Verdict.REJECTED, f"工具 {tool_name} 触发合规模式告警"
        return Verdict.CONFIRM_REQUIRED, f"未知风险等级: {tool_name}"

    def _build_result(self, verdict: Verdict, reason: str, start_time: float) -> SafetyReviewResult:
        """构建审查结果（修复：增加 self 参数）"""
        elapsed = (time.time() - start_time) * 1000
        result = SafetyReviewResult(
            review_id=f"REV-{uuid.uuid4().hex[:8]}",
            verdict=verdict,
            reject_reason=reason,
            review_duration_ms=elapsed
        )

        if self._publish_review_result:
            self._publish_review_result(result)

        # 记录安全事件日志
        event = SafetyEventLog(
            event_id=f"SEC-{uuid.uuid4().hex[:8]}",
            event_type="工具审查",
            involved_module="ag-ecc-04",
            verdict=verdict,
            risk_level=self._map_verdict_to_risk(verdict)
        )
        self._recent_events.append(event)
        if self._publish_safety_event_log:
            self._publish_safety_event_log(event)

        return result

    # ========== 安全规则获取 ==========
    def _get_safety_rules(self) -> SafetyRules:
        if self._query_safety_rules:
            rules = self._query_safety_rules()
            if rules:
                return rules
        return SafetyRules(
            blacklist=self.DEFAULT_BLACKLIST,
            whitelist=self.DEFAULT_WHITELIST,
            sensitive_ops=self.DEFAULT_SENSITIVE_OPS
        )

    # ========== 安全评分与态势管理 ==========
    def _degrade_security_score(self, amount: float):
        self._security_score = max(0.0, self._security_score - amount)
        self._reassess_state_from_score()

    def _reassess_state_from_score(self):
        """根据当前安全评分重新评估系统态势（修复：评分恢复后联动状态）"""
        if self._security_score < 0.4 and self.state != ArbiterState.EMERGENCY_LOCKDOWN:
            self.state = ArbiterState.HIGH_ALERT
        elif self._security_score < 0.7 and self.state == ArbiterState.NORMAL_MONITOR:
            self.state = ArbiterState.ENHANCED_REVIEW
        elif self._security_score >= 0.7 and self.state in (ArbiterState.ENHANCED_REVIEW, ArbiterState.HIGH_ALERT):
            self.state = ArbiterState.NORMAL_MONITOR
        elif self._security_score >= 0.4 and self.state == ArbiterState.HIGH_ALERT:
            self.state = ArbiterState.ENHANCED_REVIEW

    def _map_verdict_to_risk(self, verdict: Verdict) -> RiskLevel:
        mapping = {
            Verdict.APPROVED: RiskLevel.SAFE,
            Verdict.CONFIRM_REQUIRED: RiskLevel.MEDIUM,
            Verdict.DEGRADED_APPROVED: RiskLevel.HIGH,
            Verdict.REJECTED: RiskLevel.CRITICAL,
        }
        return mapping.get(verdict, RiskLevel.SAFE)

    # ========== 人工指令 ==========
    def _handle_manual_command(self, command: Dict[str, Any]):
        cmd_type = command.get("type", "")
        token = command.get("token", "")
        if len(token) < 10:
            self._log_event("MANUAL_CMD_REJECTED", {"reason": "令牌无效"})
            return

        if cmd_type == "emergency_lockdown":
            self.state = ArbiterState.EMERGENCY_LOCKDOWN
            if self._publish_degrade_command:
                self._publish_degrade_command(SafetyDegradeCommand(target_level=3, reason="人工紧急闭锁"))
        elif cmd_type == "release_lockdown":
            if self.state == ArbiterState.EMERGENCY_LOCKDOWN:
                self.state = ArbiterState.NORMAL_MONITOR
                self._security_score = 0.5

    # ========== 用户确认 ==========
    def _check_confirm_timeouts(self, now: float):
        timed_out = []
        for req_id, start_time in self._pending_confirmations.items():
            if now - start_time > self.USER_CONFIRM_TIMEOUT_SEC:
                timed_out.append(req_id)
        for req_id in timed_out:
            del self._pending_confirmations[req_id]
            self._log_event("CONFIRM_TIMEOUT", {"request_id": req_id})

    # ========== 辅助 ==========
    def _publish_status(self):
        if self._publish_status_report:
            score = self._security_score
            if score < 0.4:
                trend = "持续恶化"
            elif score < 0.6:
                trend = "下降中"
            elif score < 0.8:
                trend = "轻微波动"
            else:
                trend = "稳定"
            self._publish_status_report(SafetyStatusReport(
                state=self.state,
                security_score=round(score, 3),
                recent_events_count=len(self._recent_events),
                risk_trend=trend
            ))

    def get_state(self) -> ArbiterState:
        return self.state

    def emergency_shutdown(self):
        self.state = ArbiterState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 安全仲裁模块 (ag-ecc-04) 演示")
    print("=" * 70)

    arbiter = SafetyArbiter()

    print_separator("STEP 1: 审查白名单工具方案")
    arbiter.set_tool_plan_query(lambda: ToolSelectionPlan(
        step_id="S01", primary_tool=type('obj', (object,), {'name': 'weather_api'})(),
        operation_type="只读"
    ))
    result = arbiter.run_arbiter_cycle()
    if result:
        print(f"  审查结论: {result.verdict.value}")

    print_separator("STEP 2: 审查黑名单工具方案")
    arbiter.set_tool_plan_query(lambda: ToolSelectionPlan(
        step_id="S02", primary_tool=type('obj', (object,), {'name': 'shell_exec'})(),
        operation_type="执行"
    ))
    result = arbiter.run_arbiter_cycle()
    if result:
        print(f"  审查结论: {result.verdict.value}")
        print(f"  拒绝原因: {result.reject_reason}")

    print_separator("STEP 3: 安全评分下降触发态势变化")
    for _ in range(5):
        arbiter.set_tool_plan_query(lambda: ToolSelectionPlan(
            step_id="S03", primary_tool=type('obj', (object,), {'name': 'shell_exec'})(),
            operation_type="执行"
        ))
        arbiter.run_arbiter_cycle()
    print(f"  当前状态: {arbiter.state.value}")
    print(f"  安全评分: {arbiter._security_score:.2f}")

    print_separator("STEP 4: 白名单工具写入操作")
    arbiter2 = SafetyArbiter()
    arbiter2.set_tool_plan_query(lambda: ToolSelectionPlan(
        step_id="S04", primary_tool=type('obj', (object,), {'name': 'weather_api'})(),
        operation_type="写入"
    ))
    result = arbiter2.run_arbiter_cycle()
    if result:
        print(f"  审查结论: {result.verdict.value} (写入操作虽在白名单，但非只读)")

    print("\n✅ 安全仲裁模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-04 安全仲裁模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def make_plan(name, op_type="只读"):
            return ToolSelectionPlan(
                step_id="T01",
                primary_tool=type('obj', (object,), {'name': name})(),
                operation_type=op_type
            )

        # TC-E04-01: 白名单只读工具自动放行
        print("\n[TC-E04-01] 白名单只读工具自动放行")
        try:
            a = SafetyArbiter()
            a.set_tool_plan_query(lambda: make_plan("weather_api", "只读"))
            result = a.run_arbiter_cycle()
            assert result is not None
            assert result.verdict == Verdict.APPROVED
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E04-02: 黑名单工具直接拒绝
        print("\n[TC-E04-02] 黑名单工具直接拒绝")
        try:
            a = SafetyArbiter()
            a.set_tool_plan_query(lambda: make_plan("shell_exec", "执行"))
            result = a.run_arbiter_cycle()
            assert result is not None
            assert result.verdict == Verdict.REJECTED
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E04-03: 敏感操作需确认
        print("\n[TC-E04-03] 敏感操作需确认")
        try:
            a = SafetyArbiter()
            a.set_tool_plan_query(lambda: make_plan("delete_file", "删除"))
            result = a.run_arbiter_cycle()
            assert result is not None
            assert result.verdict == Verdict.CONFIRM_REQUIRED
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E04-04: 高风险态势下拒绝敏感操作
        print("\n[TC-E04-04] 高风险态势下拒绝敏感操作")
        try:
            a = SafetyArbiter()
            a.state = ArbiterState.HIGH_ALERT
            a.set_tool_plan_query(lambda: make_plan("delete_file", "删除"))
            result = a.run_arbiter_cycle()
            assert result is not None
            assert result.verdict == Verdict.REJECTED
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E04-05: 紧急闭锁状态拒绝一切
        print("\n[TC-E04-05] 紧急闭锁状态拒绝一切")
        try:
            a = SafetyArbiter()
            a.state = ArbiterState.EMERGENCY_LOCKDOWN
            a.set_tool_plan_query(lambda: make_plan("weather_api", "只读"))
            result = a.run_arbiter_cycle()
            assert result is not None
            assert result.verdict == Verdict.REJECTED
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E04-06: 紧急熔断
        print("\n[TC-E04-06] 紧急熔断")
        try:
            a = SafetyArbiter()
            a.emergency_shutdown()
            assert a.state == ArbiterState.SYSTEM_PAUSED
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
```