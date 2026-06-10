#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-11
模块名称: 抽象创造模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责: 从大量已有经验中归纳提炼通用规则、发现隐藏模式、组合已有技能生成创新解决方案。
          默认处于低功耗休眠状态，仅在收到触发信号或经验积累达到阈值时激活。
          所有创新成果在下发执行前必须通过 ag-ecc-04 安全仲裁模块的严格审查。

依赖模块: ag-ecc-05, ag-ecc-08, ag-ecc-09, ag-ecc-12
被依赖模块: ag-ecc-02, ag-ecc-05, ag-ecc-12

安全约束:
  C-01: 默认休眠，仅在显式触发且系统资源充足时激活
  C-02: 通用规则写入记忆中枢前必须通过 ag-ecc-04 审查
  C-03: 创新任务方案下发前必须通过 ag-ecc-04 审查
  C-04: 高风险操作必须经过人工审核批准
  C-05: 模式挖掘仅基于脱敏后的经验特征向量与工具序列
  C-06: 创新方案探索范围不得超出系统预设的安全边界
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging
from collections import Counter

from memory_bus import Message, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_HIGH, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-11")


class CreationState(Enum):
    DORMANT = "DORMANT"
    EXPERIENCE_FETCHING = "EXPERIENCE_FETCHING"
    PATTERN_MINING = "PATTERN_MINING"
    RULE_GENERATING = "RULE_GENERATING"
    SOLUTION_CREATING = "SOLUTION_CREATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"


class RuleType(Enum):
    TOOL_PATTERN = "工具使用模式"
    TASK_STRATEGY = "任务解决策略"
    ERROR_AVOIDANCE = "错误规避规则"
    CROSS_DOMAIN = "跨领域关联"


@dataclass
class GenericRule:
    rule_id: str = ""
    rule_description: str = ""
    applicable_scenes: List[str] = field(default_factory=list)
    source_experience_count: int = 0
    confidence: float = 0.0
    rule_type: RuleType = RuleType.TOOL_PATTERN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_description": self.rule_description,
            "applicable_scenes": self.applicable_scenes,
            "source_experience_count": self.source_experience_count,
            "confidence": self.confidence,
            "rule_type": self.rule_type.value,
        }


@dataclass
class InnovationPlan:
    plan_id: str = ""
    description: str = ""
    required_tool_combination: List[str] = field(default_factory=list)
    estimated_success_rate: float = 0.5
    risk_level: str = "低"
    innovation_basis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "description": self.description,
            "required_tool_combination": self.required_tool_combination,
            "estimated_success_rate": self.estimated_success_rate,
            "risk_level": self.risk_level,
            "innovation_basis": self.innovation_basis,
        }


class AbstractCreation:
    EXPERIENCE_ACCUMULATION_THRESHOLD = 20
    LABEL_CONSISTENCY_MIN = 0.70
    TIMED_TRIGGER_INTERVAL_SEC = 72 * 3600
    RULE_CONFIDENCE_THRESHOLD = 0.80
    HIGH_RISK_THRESHOLD = "高"
    MAX_CPU_USAGE_PCT = 70.0
    MAX_MEMORY_USAGE_PCT = 80.0
    COOLDOWN_SEC = 6 * 3600
    STATUS_REPORT_INTERVAL_SEC = 300
    MIN_SEQUENCE_LENGTH = 2
    MIN_SEQUENCE_SUPPORT = 3
    MAX_PATTERNS_PER_TYPE = 5
    SAFETY_REVIEW_TIMEOUT_SEC = 60
    APPROVAL_TIMEOUT_SEC = 120

    # C-06 工具安全白名单
    SAFE_TOOL_WHITELIST = {"tool_01", "tool_02", "tool_03", "tool_04", "tool_05"}

    def __init__(self):
        self.module_id = "ag-ecc-11"
        self.version = "V1.0"
        self.state = CreationState.DORMANT
        self.bus = None

        self._last_trigger_time: float = 0.0
        self._processed_experiences: int = 0
        self._rules_generated: int = 0
        self._plans_created: int = 0
        self._last_status_time: float = time.time()

        # 消息缓冲区
        self._triggers: List[Dict] = []
        self._innovation_drives: List[Dict] = []
        self._experience_data: List[Dict] = []
        self._approval_results: List[Dict] = []
        self._review_results: List[Dict] = []

        # 待审查任务缓存 {review_id: (数据, 提交时间)}
        self._pending_rule_reviews: Dict[str, Tuple[GenericRule, float]] = {}
        self._pending_plan_reviews: Dict[str, Tuple[InnovationPlan, float]] = {}

        logger.info("✅ 抽象创造模块初始化完成（休眠状态）")

    # ====================== 总线消息入口 ======================
    def handle_message(self, msg: Message):
        try:
            topic = msg.topic
            if topic == "ag-ecc-11.abstraction_trigger":
                self._triggers.append(msg.data)
            elif topic == "ag-ecc-11.innovation_drive":
                self._innovation_drives.append(msg.data)
            elif topic == "ag-ecc-11.experience_data":
                self._experience_data.append(msg.data)
            elif topic == "ag-ecc-11.approval_result":
                self._approval_results.append(msg.data)
            elif topic == "ag-ecc-11.review_result":
                self._review_results.append(msg.data)
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-11.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()
            elif topic == "ag-ecc-12.resume":
                if self.state == CreationState.SYSTEM_PAUSED:
                    self.state = CreationState.DORMANT
                    logger.info("▶️ 抽象创造模块恢复服务")
        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    # ====================== CPEC 主循环 ======================
    def abstract_creation_main_loop(self):
        if self.state == CreationState.SYSTEM_PAUSED:
            return

        now = time.time()

        # 定时状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 清理超时任务
        self._clean_timeout_pending(now)

        # 消费安全审查结果
        while self._review_results:
            try:
                self._handle_review_result(self._review_results.pop(0), now)
            except Exception as e:
                logger.error(f"安全审查结果处理异常: {e}")

        # 消费人工审核结果
        while self._approval_results:
            try:
                self._handle_approval(self._approval_results.pop(0), now)
            except Exception as e:
                logger.error(f"人工审核结果处理异常: {e}")

        # 非休眠状态不再接受新任务
        if self.state != CreationState.DORMANT:
            return

        # 优先级：主动触发 > 创新驱动 > 定时自动触发
        if self._triggers:
            self._handle_abstraction(self._triggers.pop(0), now)
            return

        if self._innovation_drives:
            self._handle_innovation(self._innovation_drives.pop(0), now)
            return

        # 定时自动抽象提炼
        if now - self._last_trigger_time >= self.TIMED_TRIGGER_INTERVAL_SEC:
            self._handle_abstraction({
                "trigger_type": "定时",
                "target_domain": "全量",
                "min_experience_count": self.EXPERIENCE_ACCUMULATION_THRESHOLD
            }, now)

    # ====================== 超时清理（防泄漏） ======================
    def _clean_timeout_pending(self, now: float):
        expired_rules = [rid for rid, (_, ts) in self._pending_rule_reviews.items()
                         if now - ts > self.SAFETY_REVIEW_TIMEOUT_SEC]
        for rid in expired_rules:
            self._pending_rule_reviews.pop(rid, None)
            logger.warning(f"规则审查 {rid} 超时，自动丢弃")

        expired_plans = [rid for rid, (_, ts) in self._pending_plan_reviews.items()
                        if now - ts > self.SAFETY_REVIEW_TIMEOUT_SEC]
        for rid in expired_plans:
            self._pending_plan_reviews.pop(rid, None)
            logger.warning(f"方案审查 {rid} 超时，自动丢弃")

    # ====================== 抽象提炼主流程 ======================
    def _handle_abstraction(self, data: Dict, now: float):
        if not self._check_resources():
            logger.info("系统资源不足，本次抽象提炼取消")
            return
        if now - self._last_trigger_time < self.COOLDOWN_SEC:
            logger.info("模块冷却中，暂不执行抽象提炼")
            return

        self.state = CreationState.EXPERIENCE_FETCHING
        self._last_trigger_time = now

        domain = data.get("target_domain", "")
        min_count = data.get("min_experience_count", self.EXPERIENCE_ACCUMULATION_THRESHOLD)
        experience = self._fetch_experience(domain, min_count)

        if not experience or len(experience) < min_count:
            logger.info(f"有效经验数据不足 {min_count} 条，结束本次提炼")
            self.state = CreationState.DORMANT
            return

        self.state = CreationState.PATTERN_MINING
        clean_experience = self._filter_desensitized_data(experience)
        patterns = self._mine_patterns(clean_experience, domain)

        if not patterns:
            logger.info("未挖掘到有效模式，结束本次提炼")
            self.state = CreationState.DORMANT
            return

        self.state = CreationState.RULE_GENERATING
        for pattern in patterns:
            rule = self._generate_rule(pattern, domain)
            if rule.confidence >= self.RULE_CONFIDENCE_THRESHOLD:
                self._submit_rule_review(rule, now)

        self._processed_experiences += len(experience)
        self.state = CreationState.DORMANT

    def _filter_desensitized_data(self, raw_list: List[Dict]) -> List[Dict]:
        keep_keys = {"tool_call_sequence", "task_steps", "result_label", "error_code"}
        res = []
        for item in raw_list:
            new_item = {k: v for k, v in item.items() if k in keep_keys}
            res.append(new_item)
        return res

    def _fetch_experience(self, domain: str, min_count: int) -> List[Dict]:
        if not self.bus:
            return []
        try:
            resp = self.bus.request(
                topic="ag-ecc-05.query_experience",
                source_module=self.module_id,
                target_module="ag-ecc-05",
                data={"domain": domain, "min_count": min_count},
                timeout_ms=2000
            )
        except Exception as e:
            logger.error(f"请求经验数据异常: {e}")
            return []
        return resp.data.get("entries", []) if resp else []

    # ====================== 模式挖掘算法 ======================
    def _mine_patterns(self, entries: List[Dict], domain: str) -> List[Dict]:
        patterns = []
        if not entries:
            return patterns

        total = len(entries)

        tool_sequences = [
            e.get("tool_call_sequence", [])
            for e in entries
            if isinstance(e.get("tool_call_sequence"), list)
               and len(e.get("tool_call_sequence", [])) >= self.MIN_SEQUENCE_LENGTH
        ]
        if tool_sequences:
            freq_seqs = self._find_frequent_sequences(tool_sequences, self.MIN_SEQUENCE_SUPPORT)
            for seq, freq in freq_seqs[:self.MAX_PATTERNS_PER_TYPE]:
                patterns.append({
                    "type": RuleType.TOOL_PATTERN,
                    "description": f"频繁工具调用序列: {' → '.join(seq)}",
                    "confidence": min(0.95, freq / len(tool_sequences)),
                    "total": total,
                })

        success_entries = [e for e in entries if e.get("result_label") == "成功"]
        if success_entries:
            step_counter = Counter()
            for e in success_entries:
                steps = tuple(e.get("task_steps", []))
                if steps:
                    step_counter[steps] += 1
            for steps, count in step_counter.most_common(self.MAX_PATTERNS_PER_TYPE):
                if count >= self.MIN_SEQUENCE_SUPPORT:
                    patterns.append({
                        "type": RuleType.TASK_STRATEGY,
                        "description": f"成功步骤: {' → '.join(steps)}",
                        "confidence": min(0.90, count / len(success_entries)),
                        "total": total,
                    })

        failure_entries = [e for e in entries if e.get("result_label") in ("失败", "策略失误")]
        if failure_entries:
            error_counter = Counter(e.get("error_code", "未知") for e in failure_entries)
            for error_code, count in error_counter.most_common(self.MAX_PATTERNS_PER_TYPE):
                patterns.append({
                    "type": RuleType.ERROR_AVOIDANCE,
                    "description": f"常见错误: {error_code} (出现{count}次)",
                    "confidence": min(0.85, count / len(failure_entries)),
                    "total": total,
                    "error_code": error_code,
                })

        tool_counter = Counter()
        for e in entries:
            for t in e.get("tool_call_sequence", []):
                tool_counter[t] += 1
        for tool_name, count in tool_counter.most_common(self.MAX_PATTERNS_PER_TYPE):
            if count >= self.MIN_SEQUENCE_SUPPORT:
                patterns.append({
                    "type": RuleType.CROSS_DOMAIN,
                    "description": f"高频工具 '{tool_name}' 可能跨领域适用",
                    "confidence": min(0.75, count / total),
                    "total": total,
                    "tool": tool_name,
                })

        return patterns

    def _find_frequent_sequences(self, sequences: List[List[str]], min_support: int) -> List[Tuple[List[str], int]]:
        seq_counter = Counter()
        for seq in sequences:
            n = len(seq)
            for length in range(self.MIN_SEQUENCE_LENGTH, min(5, n + 1)):
                for i in range(n - length + 1):
                    seq_counter[tuple(seq[i:i + length])] += 1
        frequent = [(list(s), c) for s, c in seq_counter.items() if c >= min_support]
        frequent.sort(key=lambda x: x[1], reverse=True)
        return frequent

    def _generate_rule(self, pattern: Dict, domain: str) -> GenericRule:
        rule_type = pattern.get("type", RuleType.TOOL_PATTERN)
        confidence = pattern.get("confidence", 0.5)
        return GenericRule(
            rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
            rule_description=pattern.get("description", ""),
            applicable_scenes=[domain] if domain else [],
            source_experience_count=pattern.get("total", 0),
            confidence=min(confidence, 1.0),
            rule_type=rule_type,
        )

    # ====================== 创新方案创建 ======================
    def _handle_innovation(self, data: Dict, now: float):
        if not self._check_resources():
            logger.info("系统资源不足，本次创新取消")
            return
        self.state = CreationState.SOLUTION_CREATING

        raw_tools = data.get("available_tools", [])[:3] or ["默认工具"]

        # 查询能力边界
        boundary = self._fetch_capability_boundary()
        known_infeasible = []
        if boundary:
            known_infeasible = boundary.get("known_infeasible_solutions", [])
            # 过滤掉已知不可行的工具组合
            if known_infeasible:
                filtered_tools = [t for t in raw_tools if t not in known_infeasible]
                if filtered_tools:
                    raw_tools = filtered_tools
                else:
                    # 全部被过滤，标记高风险并添加默认工具以避免空组合
                    raw_tools = ["默认工具"]
                    logger.warning("创新工具全部被能力边界过滤，降级为默认工具")

        # 安全白名单过滤
        safe_tools = [t for t in raw_tools if t in self.SAFE_TOOL_WHITELIST]
        if not safe_tools:
            safe_tools = ["默认工具"]

        # 根据工具组合和已知不可行性评估风险
        risk_level = "低"
        if len(safe_tools) >= 3:
            risk_level = "高"
        if known_infeasible and any(t in known_infeasible for t in safe_tools):
            # 如果仍然包含已知不可行的工具（应已过滤，但作为二次保险）
            risk_level = "高"

        plan = InnovationPlan(
            plan_id=f"INNOV-{uuid.uuid4().hex[:8]}",
            description=data.get("goal_description", ""),
            required_tool_combination=safe_tools,
            estimated_success_rate=0.5 if risk_level == "高" else 0.7,
            risk_level=risk_level,
            innovation_basis=data.get("direction", ""),
        )

        self._submit_plan_review(plan, now)
        self.state = CreationState.DORMANT

    # ====================== 能力边界查询 ======================
    def _fetch_capability_boundary(self) -> Optional[Dict[str, Any]]:
        """向 ag-ecc-08 查询能力边界信息"""
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic="ag-ecc-08.query_capability_boundary",
                source_module=self.module_id,
                target_module="ag-ecc-08",
                data={},
                timeout_ms=1000
            )
            return resp.data if resp else None
        except Exception as e:
            logger.error(f"查询能力边界异常: {e}")
            return None

    # ====================== 提交安全审查 ======================
    def _submit_rule_review(self, rule: GenericRule, submit_time: float):
        review_id = f"REV-R-{uuid.uuid4().hex[:8]}"
        self._pending_rule_reviews[review_id] = (rule, submit_time)

        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="review_request",
                source_module=self.module_id,
                data={
                    "review_id": review_id,
                    "item_type": "rule",
                    "rule_description": rule.rule_description,
                    "confidence": rule.confidence,
                },
                priority=PRIORITY_NORMAL,
            )

    def _submit_plan_review(self, plan: InnovationPlan, submit_time: float):
        review_id = f"REV-P-{uuid.uuid4().hex[:8]}"
        self._pending_plan_reviews[review_id] = (plan, submit_time)

        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="review_request",
                source_module=self.module_id,
                data={
                    "review_id": review_id,
                    "item_type": "plan",
                    "description": plan.description,
                    "tools": plan.required_tool_combination,
                    "risk_level": plan.risk_level,
                },
                priority=PRIORITY_NORMAL,
            )

    # ====================== 审查结果处理 ======================
    def _handle_review_result(self, result: Dict, now: float):
        review_id = result.get("review_id", "")
        approved = result.get("approved", False)
        reject_reason = result.get("reject_reason", "未知原因")

        if review_id in self._pending_rule_reviews:
            rule, _ = self._pending_rule_reviews.pop(review_id)
            if approved:
                self._do_publish_rule(rule)
                self._rules_generated += 1
                logger.info(f"✅ 规则 {rule.rule_id} 审查通过，已写入记忆中枢")
            else:
                logger.warning(f"❌ 规则 {rule.rule_id} 审查拒绝: {reject_reason}")
            return

        if review_id in self._pending_plan_reviews:
            plan, _ = self._pending_plan_reviews.pop(review_id)
            if approved:
                if plan.risk_level == self.HIGH_RISK_THRESHOLD:
                    self._publish_approval_request(plan)
                    self.state = CreationState.AWAITING_APPROVAL
                    logger.info(f"⚠️ 方案 {plan.plan_id} 审查通过，进入人工审核")
                else:
                    self._do_publish_plan(plan)
                    self._plans_created += 1
                    logger.info(f"✅ 方案 {plan.plan_id} 审查通过，已下发执行")
            else:
                logger.warning(f"❌ 方案 {plan.plan_id} 审查拒绝: {reject_reason}")

    # ====================== 正式下发规则/方案 ======================
    def _do_publish_rule(self, rule: GenericRule):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-05",
                event_type="generic_rule",
                source_module=self.module_id,
                data=rule.to_dict(),
                priority=PRIORITY_NORMAL,
            )

    def _do_publish_plan(self, plan: InnovationPlan):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="innovation_plan",
                source_module=self.module_id,
                data=plan.to_dict(),
                priority=PRIORITY_NORMAL,
            )

    # ====================== 人工审核流程 ======================
    def _publish_approval_request(self, plan: InnovationPlan):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="manual_approval_request",
                source_module=self.module_id,
                data={
                    "creation_id": plan.plan_id,
                    "description": plan.description,
                    "risk_description": f"高风险工具组合: {plan.required_tool_combination}",
                    "suggested_direction": "需人工审核批准",
                },
                priority=PRIORITY_HIGH,
            )

    def _handle_approval(self, data: Dict, now: float):
        creation_id = data.get("creation_id", "")
        result = data.get("result", "")

        matched_review_id = None
        target_plan = None
        for rid, (plan, ts) in self._pending_plan_reviews.items():
            if plan.plan_id == creation_id:
                matched_review_id = rid
                target_plan = plan
                break

        if matched_review_id and target_plan:
            self._pending_plan_reviews.pop(matched_review_id)
            if result == "approve":
                self._do_publish_plan(target_plan)
                self._plans_created += 1
                logger.info(f"✅ 方案 {creation_id} 人工审核通过，已下发")
            else:
                logger.warning(f"❌ 方案 {creation_id} 人工审核拒绝")

        self.state = CreationState.DORMANT

    # ====================== 状态上报 ======================
    def _publish_status(self):
        if not self.bus:
            return
        try:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="creation_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "processed_experiences": self._processed_experiences,
                    "rules_generated": self._rules_generated,
                    "plans_created": self._plans_created,
                    "pending_reviews": len(self._pending_rule_reviews) + len(self._pending_plan_reviews),
                },
                priority=PRIORITY_LOW,
            )
        except Exception as e:
            logger.error(f"状态上报异常: {e}")

    # ====================== 资源校验 ======================
    def _check_resources(self) -> bool:
        if not self.bus:
            return True
        try:
            resp = self.bus.request(
                topic="ag-ecc-12.query_resource",
                source_module=self.module_id,
                target_module="ag-ecc-12",
                data={},
                timeout_ms=1000,
            )
        except Exception as e:
            logger.error(f"资源查询异常: {e}")
            return True

        if resp and resp.data:
            cpu = resp.data.get("cpu_usage_pct", 100.0)
            mem = resp.data.get("memory_usage_pct", 100.0)
            return cpu < self.MAX_CPU_USAGE_PCT and mem < self.MAX_MEMORY_USAGE_PCT
        return True

    # ====================== 系统启停 ======================
    def emergency_shutdown(self):
        self.state = CreationState.SYSTEM_PAUSED
        logger.info("⏹️ 抽象创造模块已暂停（系统熔断）")

    def get_state(self) -> CreationState:
        return self.state