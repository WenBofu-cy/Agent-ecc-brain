#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-04
模块名称: 安全仲裁模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责:
  全局安全审查与仲裁中枢，拥有最高否决权。检测高风险时触发系统降级或紧急闭锁。
  所有待审计划/方案必须通过本模块审查方可执行。

依赖模块: ag-ecc-02, ag-ecc-03, ag-ecc-12, ag-mem-45
被依赖模块: ag-ecc-02, ag-ecc-03, ag-ecc-12, ag-mem-51

安全约束:
  A-01: 全局最高否决权
  A-02: 规则库不可用时使用内置最小规则集
  A-03: 人工安全指令需令牌验证与双重确认
  A-04: 紧急闭锁仅人工解除
  A-05: 用户确认请求超时 60 秒
  A-06: 安全事件日志完整记录
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

# 标准化总线导入（与主入口保持一致）
from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-04")


# ==================== 枚举与数据结构 ====================
class ArbiterState(Enum):
    NORMAL_MONITOR = "normal_monitor"
    ENHANCED_REVIEW = "enhanced_review"
    HIGH_ALERT = "high_alert"
    EMERGENCY_LOCKDOWN = "emergency_lockdown"
    SYSTEM_PAUSED = "system_paused"


class RiskLevel(Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    EXTREME = "EXTREME"


class Verdict(Enum):
    APPROVED = "APPROVED"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    REJECTED = "REJECTED"
    DEGRADED_APPROVED = "DEGRADED_APPROVED"


@dataclass
class SafetyRules:
    blacklist: List[str] = field(default_factory=list)
    whitelist: List[str] = field(default_factory=list)
    sensitive_ops: List[str] = field(default_factory=list)
    compliance_patterns: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SafetyReviewResult:
    review_id: str = ""
    verdict: Verdict = Verdict.APPROVED
    reject_reason: str = ""
    additional_constraints: Dict[str, Any] = field(default_factory=dict)
    review_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "verdict": self.verdict.value,
            "reject_reason": self.reject_reason,
            "additional_constraints": self.additional_constraints,
            "review_duration_ms": self.review_duration_ms,
        }


class SafetyArbiter:
    """安全仲裁模块 V1.0（标准化重构版）"""

    # 内置最小安全规则集（CPEC A-02）
    DEFAULT_BLACKLIST = ["shell_exec", "db_delete", "system_restart", "format_drive"]
    DEFAULT_WHITELIST = ["weather_api", "file_read", "text_generator", "search_engine"]
    DEFAULT_SENSITIVE_OPS = ["delete_file", "modify_config", "write_system", "grant_permission"]

    USER_CONFIRM_TIMEOUT_SEC = 60          # A-05
    STATUS_REPORT_INTERVAL_SEC = 60
    SECURITY_SCORE_RECOVERY_RATE = 0.01
    RULES_CACHE_TTL_SEC = 300

    def __init__(self):
        self.module_id = "ag-ecc-04"
        self.version = "V1.0"
        self.state = ArbiterState.NORMAL_MONITOR
        self.bus = None  # 由主入口注入

        self._security_score = 0.85
        self._pending_confirmations: Dict[str, dict] = {}
        self._last_status_time = time.time()

        self._cached_rules: Optional[SafetyRules] = None
        self._rules_cache_time = 0.0

        # 缓冲区：待处理的审查请求（统一由主循环顺序处理）
        self._review_queue: List[Dict[str, Any]] = []
        # 人工指令缓冲区
        self._manual_commands: List[Dict[str, Any]] = []

        logger.info("安全仲裁模块初始化完成")

    # ====================== 总线消息入口（标准注入） ======================
    def handle_message(self, msg: Message):
        """接收并缓存各类消息，由主循环统一处理（单线程安全）"""
        try:
            topic = msg.topic

            if topic == "ag-ecc-04.review_request":
                # 将数据与来源模块一起缓存，用于后续路由
                self._review_queue.append({
                    "data": msg.data,
                    "source_module": msg.source_module
                })
                logger.debug(f"审查请求已入队，当前队列长度: {len(self._review_queue)}")

            elif topic == "ag-ecc-04.manual_command":
                self._manual_commands.append(msg.data)

            elif topic == "ag-ecc-04.confirm_response":
                self._handle_confirm_response(msg.data)

            elif topic == "ag-ecc-04.shutdown":
                self.emergency_shutdown()

            elif topic == "ag-ecc-04.resume":
                if self.state == ArbiterState.SYSTEM_PAUSED:
                    self.state = ArbiterState.NORMAL_MONITOR
                    logger.info("安全仲裁恢复服务")

        except Exception as e:
            logger.error(f"处理消息异常: {str(e)}", exc_info=True)

    # ====================== 主循环（CPEC 规定入口） ======================
    def safety_arbiter_main_loop(self):
        """主循环：处理缓冲区的审查请求、人工指令、超时清理与状态维护"""
        if self.state == ArbiterState.SYSTEM_PAUSED:
            return

        now = time.time()

        # 1. 处理人工指令（优先级最高）
        while self._manual_commands:
            cmd = self._manual_commands.pop(0)
            self._process_manual_command(cmd)

        # 2. 处理待审查请求（FIFO）
        while self._review_queue:
            item = self._review_queue.pop(0)
            self._process_review_request(item)

        # 3. 定时状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 4. 安全评分缓慢恢复
        if self.state != ArbiterState.EMERGENCY_LOCKDOWN:
            self._security_score = min(1.0, self._security_score + self.SECURITY_SCORE_RECOVERY_RATE)
            self._reassess_state()

        # 5. 清理超时确认请求 (A-05)
        expired = [
            rid for rid, ctx in self._pending_confirmations.items()
            if now - ctx["timestamp"] > self.USER_CONFIRM_TIMEOUT_SEC
        ]
        for rid in expired:
            ctx = self._pending_confirmations.pop(rid)
            result = SafetyReviewResult(
                review_id=f"REV-{uuid.uuid4().hex[:8]}",
                verdict=Verdict.REJECTED,
                reject_reason="用户确认超时（60s）"
            )
            self._send_review_result(ctx["source_module"], result)
            self._log_safety_event(ctx["source_module"], result)
            logger.info(f"确认请求超时自动拒绝: {rid}")

    # ====================== 审查逻辑（内部方法） ======================
    def _process_review_request(self, item: Dict[str, Any]):
        """统一审查入口：根据来源模块选择审查方法"""
        data = item["data"]
        source_module = item["source_module"]
        start_time = time.time()

        # 根据来源模块选择审查逻辑：ag-ecc-02 发送的是任务计划，其他发送的是工具方案
        if source_module == "ag-ecc-02":
            result = self._review_task_plan(data)
        else:
            result = self._review_tool_plan(data)

        result.review_duration_ms = round((time.time() - start_time) * 1000, 2)

        # 需要用户确认 → 暂存并发起请求
        if result.verdict == Verdict.CONFIRM_REQUIRED:
            request_id = f"CFM-{uuid.uuid4().hex[:8]}"
            self._pending_confirmations[request_id] = {
                "source_module": source_module,
                "timestamp": time.time()
            }
            self._send_confirm_request(request_id, data)
            return

        # 直接返回审查结果
        self._send_review_result(source_module, result)
        self._log_safety_event(source_module, result)

    def _review_task_plan(self, data: Dict[str, Any]) -> SafetyReviewResult:
        """审查任务计划：检查每个步骤中的工具是否在黑名单"""
        rules = self._get_safety_rules()
        steps = data.get("steps", [])
        for step in steps:
            tool_name = step.get("required_tool_type", "")
            if tool_name in rules.blacklist:
                return SafetyReviewResult(
                    review_id=f"REV-{uuid.uuid4().hex[:8]}",
                    verdict=Verdict.REJECTED,
                    reject_reason=f"步骤涉及黑名单工具: {tool_name}"
                )
        return SafetyReviewResult(
            review_id=f"REV-{uuid.uuid4().hex[:8]}",
            verdict=Verdict.APPROVED
        )

    def _review_tool_plan(self, data: Dict[str, Any]) -> SafetyReviewResult:
        """审查工具选择方案"""
        if self.state == ArbiterState.EMERGENCY_LOCKDOWN:
            return SafetyReviewResult(
                review_id=f"REV-{uuid.uuid4().hex[:8]}",
                verdict=Verdict.REJECTED,
                reject_reason="系统处于紧急闭锁状态"
            )

        rules = self._get_safety_rules()
        tool_name = data.get("tool_name", "")
        if not tool_name:
            return SafetyReviewResult(
                review_id=f"REV-{uuid.uuid4().hex[:8]}",
                verdict=Verdict.REJECTED,
                reject_reason="无法获取工具名称"
            )

        risk = self._assess_risk_level(tool_name, data, rules)
        verdict, reason = self._determine_verdict(risk, tool_name)

        # 动态调整安全评分
        if risk in (RiskLevel.CRITICAL, RiskLevel.EXTREME):
            self._degrade_security_score(0.2)
        elif risk == RiskLevel.HIGH:
            self._degrade_security_score(0.1)

        return SafetyReviewResult(
            review_id=f"REV-{uuid.uuid4().hex[:8]}",
            verdict=verdict,
            reject_reason=reason
        )

    def _assess_risk_level(self, tool_name: str, data: Dict[str, Any], rules: SafetyRules) -> RiskLevel:
        """评估工具风险等级"""
        if tool_name in rules.blacklist:
            return RiskLevel.CRITICAL
        if self._match_compliance_patterns(tool_name, rules.compliance_patterns):
            return RiskLevel.EXTREME
        if tool_name in rules.whitelist:
            op_type = data.get("operation_type", "只读")
            return RiskLevel.SAFE if op_type in ("只读", "read", "READ") else RiskLevel.LOW
        if tool_name in rules.sensitive_ops:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    def _match_compliance_patterns(self, tool_name: str, patterns: List[Dict[str, Any]]) -> bool:
        """检查工具是否命中合规模式"""
        return any(tool_name in p.get("tools", []) for p in patterns)

    def _determine_verdict(self, risk: RiskLevel, tool_name: str) -> tuple:
        """根据风险等级和当前安全态势综合判定审查结论"""
        # 高风险态势下拒绝中风险及以上操作
        if self.state == ArbiterState.HIGH_ALERT and risk in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.EXTREME):
            return Verdict.REJECTED, f"高风险态势下拒绝{risk.value}操作: {tool_name}"

        # 加强审查下高风险操作需用户确认
        if self.state == ArbiterState.ENHANCED_REVIEW and risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return Verdict.CONFIRM_REQUIRED, f"加强审查下{risk.value}操作需确认: {tool_name}"

        # 标准风险判定
        mapping = {
            RiskLevel.SAFE: (Verdict.APPROVED, ""),
            RiskLevel.LOW: (Verdict.APPROVED, ""),
            RiskLevel.MEDIUM: (Verdict.CONFIRM_REQUIRED, f"工具 {tool_name} 不在白名单，需用户确认"),
            RiskLevel.HIGH: (Verdict.CONFIRM_REQUIRED, f"敏感操作需用户确认: {tool_name}"),
            RiskLevel.CRITICAL: (Verdict.REJECTED, f"工具 {tool_name} 在黑名单中，拒绝执行"),
            RiskLevel.EXTREME: (Verdict.REJECTED, f"工具 {tool_name} 触发合规模式告警，系统已紧急闭锁"),
        }
        verdict, reason = mapping.get(risk, (Verdict.CONFIRM_REQUIRED, "未知风险等级"))

        # 极端风险触发紧急闭锁（统一在此处处理，避免重复）
        if risk == RiskLevel.EXTREME:
            self._trigger_emergency_lockdown(tool_name)

        return verdict, reason

    # ====================== 用户确认 ======================
    def _send_confirm_request(self, request_id: str, data: Dict[str, Any]):
        """向用户发起确认请求"""
        if self.bus:
            rules = self._get_safety_rules()
            risk = self._assess_risk_level(data.get("tool_name", ""), data, rules)
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="user_confirm_request",
                source_module=self.module_id,
                data={
                    "request_id": request_id,
                    "operation_description": f"工具调用: {data.get('tool_name', '未知')}",
                    "risk_description": f"风险等级: {risk.value}",
                    "options": ["确认执行", "取消"],
                    "timeout_sec": self.USER_CONFIRM_TIMEOUT_SEC
                },
                priority=PRIORITY_HIGH
            )

    def _handle_confirm_response(self, data: Dict[str, Any]):
        """处理用户确认响应"""
        request_id = data.get("request_id", "")
        user_choice = data.get("choice", "取消")
        pending = self._pending_confirmations.pop(request_id, None)
        if not pending:
            logger.warning(f"无效的确认响应: {request_id}")
            return

        if user_choice == "确认执行":
            result = SafetyReviewResult(
                review_id=f"REV-{uuid.uuid4().hex[:8]}",
                verdict=Verdict.APPROVED
            )
        else:
            result = SafetyReviewResult(
                review_id=f"REV-{uuid.uuid4().hex[:8]}",
                verdict=Verdict.REJECTED,
                reject_reason="用户取消执行"
            )

        self._send_review_result(pending["source_module"], result)
        self._log_safety_event(pending["source_module"], result)

    # ====================== 人工指令 ======================
    def _process_manual_command(self, cmd: Dict[str, Any]):
        """A-03/A-04 令牌验证与双重确认"""
        token = cmd.get("token", "")
        if not token or len(token) < 16:
            logger.warning("人工指令令牌无效或过短，拒绝执行")
            return

        if cmd.get("confirm_count", 0) < 2:
            logger.warning("人工指令未完成双重确认，拒绝执行")
            return

        cmd_type = cmd.get("type", "")
        if cmd_type == "emergency_lockdown":
            self.state = ArbiterState.EMERGENCY_LOCKDOWN
            self._send_degrade_command("emergency_lockdown", 3, "人工触发紧急闭锁")
            logger.critical("人工指令：系统进入紧急闭锁状态")

        elif cmd_type == "release_lockdown":
            if self.state == ArbiterState.EMERGENCY_LOCKDOWN:
                self.state = ArbiterState.NORMAL_MONITOR
                self._security_score = 0.5
                logger.info("人工指令：紧急闭锁已解除")

    # ====================== 通信辅助 ======================
    def _get_safety_rules(self) -> SafetyRules:
        """获取安全规则，带缓存和降级（A-02）"""
        now = time.time()
        if self._cached_rules and (now - self._rules_cache_time) < self.RULES_CACHE_TTL_SEC:
            return self._cached_rules

        rules = SafetyRules(
            blacklist=self.DEFAULT_BLACKLIST,
            whitelist=self.DEFAULT_WHITELIST,
            sensitive_ops=self.DEFAULT_SENSITIVE_OPS
        )

        if self.bus:
            try:
                resp = self.bus.request(
                    topic="ag-mem-45.query_safety_rules",
                    source_module=self.module_id,
                    data={},
                    target_module="ag-mem-45",
                    timeout_ms=1000
                )
                if resp and resp.data:
                    rules = SafetyRules(
                        blacklist=resp.data.get("blacklist", self.DEFAULT_BLACKLIST),
                        whitelist=resp.data.get("whitelist", self.DEFAULT_WHITELIST),
                        sensitive_ops=resp.data.get("sensitive_ops", self.DEFAULT_SENSITIVE_OPS),
                        compliance_patterns=resp.data.get("compliance_patterns", [])
                    )
                    self._cached_rules = rules
                    self._rules_cache_time = now
            except Exception as e:
                logger.warning(f"获取安全规则失败，使用内置最小规则集: {e}")

        return rules

    def _send_review_result(self, target: str, result: SafetyReviewResult):
        """将审查结果发送给指定模块"""
        if self.bus:
            self.bus.publish_to_module(
                target_module=target,
                event_type="review_result",
                source_module=self.module_id,
                data=result.to_dict(),
                priority=PRIORITY_HIGH
            )

    def _log_safety_event(self, source: str, result: SafetyReviewResult):
        """记录安全事件日志至 ag-mem-51"""
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-mem-51",
                event_type="safety_event",
                source_module=self.module_id,
                data={
                    "event_id": f"SEC-{uuid.uuid4().hex[:8]}",
                    "event_type": "安全审查",
                    "involved_module": source,
                    "verdict": result.verdict.value,
                    "reject_reason": result.reject_reason,
                    "timestamp": time.time()
                },
                priority=PRIORITY_NORMAL
            )

    def _send_degrade_command(self, cmd_type: str, level: int, reason: str):
        """向资源调度模块发送降级/闭锁指令"""
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="degrade_command",
                source_module=self.module_id,
                data={"command_type": cmd_type, "target_level": level, "reason": reason},
                priority=PRIORITY_CRITICAL
            )

    def _trigger_emergency_lockdown(self, tool_name: str):
        """触发紧急闭锁"""
        self.state = ArbiterState.EMERGENCY_LOCKDOWN
        self._send_degrade_command("emergency_lockdown", 3, f"检测到极端风险工具: {tool_name}")
        logger.critical(f"极端风险触发紧急闭锁: {tool_name}")

    def _degrade_security_score(self, amount: float):
        """降低安全评分"""
        self._security_score = max(0.0, self._security_score - amount)
        self._reassess_state()

    def _reassess_state(self):
        """根据安全评分重新评估安全态势"""
        if self._security_score < 0.4 and self.state != ArbiterState.EMERGENCY_LOCKDOWN:
            self.state = ArbiterState.HIGH_ALERT
        elif 0.4 <= self._security_score < 0.7 and self.state == ArbiterState.NORMAL_MONITOR:
            self.state = ArbiterState.ENHANCED_REVIEW
        elif self._security_score >= 0.7 and self.state in (ArbiterState.ENHANCED_REVIEW, ArbiterState.HIGH_ALERT):
            self.state = ArbiterState.NORMAL_MONITOR

    def _publish_status(self):
        """向 ag-ecc-12 上报安全态势"""
        if self.bus:
            trend = "稳定" if self._security_score >= 0.8 else "轻微波动"
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="safety_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "security_score": round(self._security_score, 3),
                    "risk_trend": trend
                },
                priority=PRIORITY_NORMAL
            )

    def emergency_shutdown(self):
        """紧急熔断（系统级）"""
        self.state = ArbiterState.SYSTEM_PAUSED
        logger.info("安全仲裁模块已暂停（系统级熔断）")
        logger.warning("安全仲裁紧急停机 - 时间戳: %s", time.time())

    def get_state(self) -> ArbiterState:
        return self.state