#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-11
模块名称: 抽象创造模块
所属分区: 一、认知大脑核心模块
核心职责: 从大量已有经验中归纳提炼通用规则、发现隐藏模式、组合已有技能生成创新解决方案。
          支持四维规则生成：工具使用模式、任务解决策略、错误规避规则、跨领域关联。
          默认处于低功耗休眠状态，仅在收到触发信号或经验积累达到阈值时激活。
          所有创新成果在下发执行前必须通过 ag-ecc-04 安全仲裁模块的严格审查。

依赖模块:
    ag-ecc-05(记忆查询模块), ag-ecc-08(元认知模块),
    ag-ecc-09(内生动机模块), ag-ecc-12(资源调度模块)
被依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-05, ag-ecc-12

安全约束:
  C-01: 本模块默认处于休眠状态，仅在被显式触发且系统资源充足时激活
  C-02: 所有生成的通用规则在写入记忆中枢前必须通过 ag-ecc-04 安全仲裁模块的审查
  C-03: 所有创新任务方案在下发执行前必须通过 ag-ecc-04 安全仲裁模块的审查
  C-04: 涉及高风险操作的创新方案必须经过人工审核批准，不得自动执行
  C-05: 模式挖掘仅基于脱敏后的经验特征向量与工具序列，不得访问用户原始输入
  C-06: 创新方案的探索范围不得超出系统预设的安全边界
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import math
from collections import Counter, defaultdict


class CreationState(Enum):
    DORMANT = "dormant"
    EXPERIENCE_FETCHING = "experience_fetching"
    PATTERN_MINING = "pattern_mining"
    RULE_GENERATING = "rule_generating"
    SOLUTION_CREATING = "solution_creating"
    AWAITING_APPROVAL = "awaiting_approval"
    SYSTEM_PAUSED = "system_paused"


class RuleType(Enum):
    TOOL_PATTERN = "工具使用模式"
    TASK_STRATEGY = "任务解决策略"
    ERROR_AVOIDANCE = "错误规避规则"
    CROSS_DOMAIN = "跨领域关联"


@dataclass
class AbstractionTrigger:
    trigger_type: str = "经验累积"
    target_domain: str = ""
    min_experience_count: int = 20
    expected_output: str = "通用规则"


@dataclass
class ExperienceData:
    domain: str = ""
    entries: List[Dict[str, Any]] = field(default_factory=list)
    time_range: Tuple[float, float] = (0.0, 0.0)
    total_count: int = 0


@dataclass
class CapabilityBoundary:
    current_weaknesses: List[str] = field(default_factory=list)
    known_infeasible_solutions: List[str] = field(default_factory=list)
    historical_innovation_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class InnovationDrive:
    direction: str = ""
    available_tools: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    goal_description: str = ""


@dataclass
class GenericRule:
    rule_id: str = ""
    rule_description: str = ""
    applicable_scenes: List[str] = field(default_factory=list)
    source_experience_count: int = 0
    confidence: float = 0.0
    rule_type: RuleType = RuleType.TOOL_PATTERN


@dataclass
class InnovationPlan:
    plan_id: str = ""
    description: str = ""
    required_tool_combination: List[str] = field(default_factory=list)
    estimated_success_rate: float = 0.5
    risk_level: str = "低"
    innovation_basis: str = ""


@dataclass
class ManualApprovalRequest:
    creation_id: str = ""
    description: str = ""
    risk_description: str = ""
    suggested_direction: str = ""
    timeout_sec: int = 3600


@dataclass
class CreationStatus:
    state: CreationState = CreationState.DORMANT
    processed_experiences: int = 0
    rules_generated: int = 0
    plans_created: int = 0
    resource_consumption: float = 0.0


class AbstractCreation:
    # 触发阈值
    EXPERIENCE_ACCUMULATION_THRESHOLD = 20
    LABEL_CONSISTENCY_MIN = 0.70
    TIMED_TRIGGER_INTERVAL_SEC = 72 * 3600
    RULE_CONFIDENCE_THRESHOLD = 0.80
    HIGH_RISK_THRESHOLD = "高"

    # 资源限制
    MAX_CPU_USAGE_PCT = 70.0
    MAX_MEMORY_USAGE_PCT = 80.0
    COOLDOWN_SEC = 6 * 3600

    # 状态上报间隔
    STATUS_REPORT_INTERVAL_SEC = 300

    # 序列挖掘阈值
    MIN_SEQUENCE_LENGTH = 2
    MIN_SEQUENCE_SUPPORT = 3
    MAX_PATTERNS_PER_TYPE = 5

    def __init__(self):
        self.module_id = "ag-ecc-11"
        self.module_name = "抽象创造模块"
        self.version = "V1.0"

        self.state = CreationState.DORMANT
        self._last_trigger_time: float = 0.0
        self._processed_experiences: int = 0
        self._rules_generated: int = 0
        self._plans_created: int = 0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_abstraction_trigger = None
        self._query_innovation_drive = None
        self._query_experience_data = None
        self._query_capability_boundary = None
        self._query_manual_approval = None
        self._query_resource_status = None

        self._publish_generic_rule = None
        self._publish_innovation_plan = None
        self._publish_manual_approval_request = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成 (休眠状态)")

    # ========== 回调注入 ==========
    def set_abstraction_trigger_query(self, callback: Callable[[], Optional[AbstractionTrigger]]):
        self._query_abstraction_trigger = callback

    def set_innovation_drive_query(self, callback: Callable[[], Optional[InnovationDrive]]):
        self._query_innovation_drive = callback

    def set_experience_data_query(self, callback: Callable[[str, int], Optional[ExperienceData]]):
        self._query_experience_data = callback

    def set_capability_boundary_query(self, callback: Callable[[], Optional[CapabilityBoundary]]):
        self._query_capability_boundary = callback

    def set_manual_approval_query(self, callback: Callable[[], Optional[Dict[str, Any]]]):
        self._query_manual_approval = callback

    def set_resource_status_query(self, callback: Callable[[], Optional[Dict[str, Any]]]):
        self._query_resource_status = callback

    def set_generic_rule_publisher(self, callback: Callable[[GenericRule], None]):
        self._publish_generic_rule = callback

    def set_innovation_plan_publisher(self, callback: Callable[[InnovationPlan], None]):
        self._publish_innovation_plan = callback

    def set_manual_approval_request_publisher(self, callback: Callable[[ManualApprovalRequest], None]):
        self._publish_manual_approval_request = callback

    def set_status_report_publisher(self, callback: Callable[[CreationStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_creation_cycle(self):
        now = time.time()

        if self.state == CreationState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理人工审核结果
        if self.state == CreationState.AWAITING_APPROVAL:
            approval = self._query_manual_approval() if self._query_manual_approval else None
            if approval:
                self._handle_approval(approval)
                self.state = CreationState.DORMANT
            return

        # 休眠状态检查触发
        if self.state == CreationState.DORMANT:
            trigger = self._query_abstraction_trigger() if self._query_abstraction_trigger else None
            innovation = self._query_innovation_drive() if self._query_innovation_drive else None

            if trigger:
                self._handle_abstraction(trigger, now)
            elif innovation:
                self._handle_innovation(innovation, now)
            elif now - self._last_trigger_time >= self.TIMED_TRIGGER_INTERVAL_SEC:
                self._handle_abstraction(
                    AbstractionTrigger(trigger_type="定时", target_domain="全量",
                                       min_experience_count=self.EXPERIENCE_ACCUMULATION_THRESHOLD),
                    now
                )

    # ========== 抽象提炼 ==========
    def _handle_abstraction(self, trigger: AbstractionTrigger, now: float):
        if not self._check_resources():
            self._log_event("ABSTRACTION_DEFERRED", {"reason": "系统资源不足"})
            return

        if now - self._last_trigger_time < self.COOLDOWN_SEC:
            return

        self.state = CreationState.EXPERIENCE_FETCHING
        self._last_trigger_time = now

        if self._query_experience_data:
            experience = self._query_experience_data(trigger.target_domain, trigger.min_experience_count)
        else:
            experience = ExperienceData()

        if experience.total_count < trigger.min_experience_count:
            self.state = CreationState.DORMANT
            return

        self.state = CreationState.PATTERN_MINING
        patterns = self._mine_patterns(experience)

        if not patterns:
            self.state = CreationState.DORMANT
            return

        self.state = CreationState.RULE_GENERATING
        for pattern in patterns:
            rule = self._generate_rule(pattern, experience)
            if rule.confidence >= self.RULE_CONFIDENCE_THRESHOLD:
                if self._publish_generic_rule:
                    self._publish_generic_rule(rule)
                self._rules_generated += 1

        self._processed_experiences += experience.total_count
        self.state = CreationState.DORMANT

    def _mine_patterns(self, experience: ExperienceData) -> List[Dict[str, Any]]:
        """
        增强的多维度模式挖掘：
        1. 工具使用模式 - 挖掘高频工具调用序列
        2. 任务解决策略 - 统计成功的步骤模式
        3. 错误规避规则 - 统计失败经验中的错误码分布
        4. 跨领域关联 - 发现不同领域的共同工具
        """
        patterns = []
        if not experience.entries:
            return patterns

        # 维度1：工具使用模式 - 挖掘频繁工具调用序列
        tool_sequences = []
        for entry in experience.entries:
            tools = entry.get("tool_call_sequence", [])
            if isinstance(tools, list) and len(tools) >= self.MIN_SEQUENCE_LENGTH:
                tool_sequences.append(tools)

        if tool_sequences:
            freq_seqs = self._find_frequent_sequences(tool_sequences, self.MIN_SEQUENCE_SUPPORT)
            for seq, freq in freq_seqs[:self.MAX_PATTERNS_PER_TYPE]:
                patterns.append({
                    "type": RuleType.TOOL_PATTERN,
                    "description": f"频繁工具调用序列: {' → '.join(seq)}",
                    "frequency": freq,
                    "total": len(tool_sequences),
                    "confidence": min(0.95, freq / len(tool_sequences)),
                    "sequence": seq
                })

        # 维度2：任务解决策略 - 统计成功经验的步骤模式
        success_entries = [e for e in experience.entries if e.get("result_label") == "成功"]
        if success_entries:
            step_patterns = Counter()
            for entry in success_entries:
                steps = entry.get("task_steps", [])
                if isinstance(steps, list) and steps:
                    step_patterns[tuple(steps)] += 1

            for step_tuple, count in step_patterns.most_common(self.MAX_PATTERNS_PER_TYPE):
                if count >= self.MIN_SEQUENCE_SUPPORT:
                    patterns.append({
                        "type": RuleType.TASK_STRATEGY,
                        "description": f"成功任务的步骤模式: {' → '.join(step_tuple)}",
                        "frequency": count,
                        "total": len(success_entries),
                        "confidence": min(0.90, count / len(success_entries)),
                        "steps": list(step_tuple)
                    })

        # 维度3：错误规避规则 - 统计失败经验中的错误码分布
        failure_entries = [e for e in experience.entries if e.get("result_label") in ("失败", "策略失误")]
        if failure_entries:
            error_counter = Counter()
            for entry in failure_entries:
                error_code = entry.get("error_code", "未知错误")
                if error_code:
                    error_counter[error_code] += 1

            for error_code, count in error_counter.most_common(self.MAX_PATTERNS_PER_TYPE):
                patterns.append({
                    "type": RuleType.ERROR_AVOIDANCE,
                    "description": f"常见错误: {error_code} (出现{count}次)",
                    "frequency": count,
                    "total": len(failure_entries),
                    "confidence": min(0.85, count / len(failure_entries)),
                    "error_code": error_code
                })

        # 维度4：跨领域关联 - 发现不同领域共用的工具
        # (简化实现：按工具名跨领域统计)
        if hasattr(experience, 'domain') and experience.domain:
            # 这里可以结合记忆中枢查询其他领域的经验进行交叉分析
            # 当前简化：统计当前经验中的工具分布
            tool_counter = Counter()
            for entry in experience.entries:
                tools = entry.get("tool_call_sequence", [])
                if isinstance(tools, list):
                    for t in tools:
                        tool_counter[t] += 1

            # 高频工具且出现在多个条目中，可能具有跨领域迁移性
            for tool_name, count in tool_counter.most_common(self.MAX_PATTERNS_PER_TYPE):
                if count >= self.MIN_SEQUENCE_SUPPORT:
                    patterns.append({
                        "type": RuleType.CROSS_DOMAIN,
                        "description": f"高频工具 '{tool_name}' 可能在多个领域中适用",
                        "frequency": count,
                        "total": experience.total_count,
                        "confidence": min(0.75, count / experience.total_count),
                        "tool": tool_name
                    })

        # 保留原有的标签分布模式作为兜底
        label_counts: Dict[str, int] = {}
        for entry in experience.entries:
            label = entry.get("result_label", "未知")
            label_counts[label] = label_counts.get(label, 0) + 1

        dominant_label = max(label_counts, key=label_counts.get) if label_counts else None
        if dominant_label and (label_counts[dominant_label] / experience.total_count) >= self.LABEL_CONSISTENCY_MIN:
            # 避免重复添加已覆盖的模式
            if not any(p.get("type") == RuleType.TOOL_PATTERN for p in patterns):
                patterns.append({
                    "type": RuleType.TOOL_PATTERN,
                    "description": f"结果标签分布: '{dominant_label}' 占比 {label_counts[dominant_label]/experience.total_count:.0%}",
                    "frequency": label_counts[dominant_label],
                    "total": experience.total_count,
                    "confidence": label_counts[dominant_label] / experience.total_count,
                })

        return patterns

    def _find_frequent_sequences(self, sequences: List[List[str]], min_support: int) -> List[Tuple[List[str], int]]:
        """
        简化的频繁序列挖掘：
        使用滑动窗口提取所有长度为2-4的子序列，统计出现频率。
        """
        seq_counter = Counter()
        for seq in sequences:
            n = len(seq)
            for length in range(self.MIN_SEQUENCE_LENGTH, min(5, n + 1)):
                for i in range(n - length + 1):
                    subseq = tuple(seq[i:i + length])
                    seq_counter[subseq] += 1

        # 筛选支持度达标的序列，按频率降序排列
        frequent = [(list(seq), count) for seq, count in seq_counter.items() if count >= min_support]
        frequent.sort(key=lambda x: x[1], reverse=True)
        return frequent

    def _generate_rule(self, pattern: Dict[str, Any], experience: ExperienceData) -> GenericRule:
        """
        根据模式类型生成对应的通用规则。
        """
        rule_type = pattern.get("type", RuleType.TOOL_PATTERN)
        confidence = pattern.get("confidence", 0.5)
        count_norm = min(pattern.get("total", 0) / 20.0, 1.0)
        final_confidence = round(0.5 * confidence + 0.3 * count_norm + 0.2, 3)

        if rule_type == RuleType.TOOL_PATTERN:
            description = pattern.get("description", "")
            scene = [experience.domain] if experience.domain else []
            rule = GenericRule(
                rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
                rule_description=f"[工具使用模式] {description}",
                applicable_scenes=scene,
                source_experience_count=pattern.get("total", 0),
                confidence=min(final_confidence, 1.0),
                rule_type=rule_type
            )

        elif rule_type == RuleType.TASK_STRATEGY:
            description = pattern.get("description", "")
            rule = GenericRule(
                rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
                rule_description=f"[任务解决策略] {description}",
                applicable_scenes=[experience.domain] if experience.domain else [],
                source_experience_count=pattern.get("total", 0),
                confidence=min(final_confidence, 1.0),
                rule_type=rule_type
            )

        elif rule_type == RuleType.ERROR_AVOIDANCE:
            error_code = pattern.get("error_code", "未知")
            rule = GenericRule(
                rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
                rule_description=f"[错误规避] 避免在{experience.domain}领域遇到'{error_code}'错误，建议提前检查参数或权限",
                applicable_scenes=[experience.domain] if experience.domain else [],
                source_experience_count=pattern.get("total", 0),
                confidence=min(final_confidence, 1.0),
                rule_type=rule_type
            )

        elif rule_type == RuleType.CROSS_DOMAIN:
            tool = pattern.get("tool", "")
            rule = GenericRule(
                rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
                rule_description=f"[跨领域关联] 工具'{tool}'在多个领域中被频繁使用，可能具有跨领域迁移性",
                applicable_scenes=["多领域"],
                source_experience_count=pattern.get("total", 0),
                confidence=min(final_confidence, 1.0),
                rule_type=rule_type
            )

        else:
            # 兜底
            rule = GenericRule(
                rule_id=f"RULE-{uuid.uuid4().hex[:8]}",
                rule_description=pattern.get("description", ""),
                applicable_scenes=[experience.domain] if experience.domain else [],
                source_experience_count=pattern.get("total", 0),
                confidence=min(final_confidence, 1.0),
                rule_type=RuleType.TOOL_PATTERN
            )

        return rule

    # ========== 创新方案创建 ==========
    def _handle_innovation(self, drive: InnovationDrive, now: float):
        if not self._check_resources():
            return

        self.state = CreationState.SOLUTION_CREATING

        boundary = self._query_capability_boundary() if self._query_capability_boundary else CapabilityBoundary()

        tool_combination = drive.available_tools[:3] if drive.available_tools else ["默认工具"]

        risk_level = "低"
        if len(tool_combination) >= 3:
            risk_level = "中"
        if any(t in boundary.known_infeasible_solutions for t in tool_combination):
            risk_level = "高"

        plan = InnovationPlan(
            plan_id=f"INNOV-{uuid.uuid4().hex[:8]}",
            description=f"创新探索: {drive.goal_description}",
            required_tool_combination=tool_combination,
            estimated_success_rate=0.5 if risk_level == "高" else 0.7,
            risk_level=risk_level,
            innovation_basis=f"方向: {drive.direction}"
        )

        if risk_level == self.HIGH_RISK_THRESHOLD:
            self.state = CreationState.AWAITING_APPROVAL
            if self._publish_manual_approval_request:
                self._publish_manual_approval_request(ManualApprovalRequest(
                    creation_id=plan.plan_id,
                    description=plan.description,
                    risk_description=f"涉及高风险工具组合: {tool_combination}",
                    suggested_direction="需人工审核批准"
                ))
        else:
            if self._publish_innovation_plan:
                self._publish_innovation_plan(plan)
            self._plans_created += 1
            self.state = CreationState.DORMANT

    def _handle_approval(self, approval: Dict[str, Any]):
        result = approval.get("result", "reject")
        if result == "approve":
            plan = InnovationPlan(
                plan_id=approval.get("creation_id", ""),
                description=approval.get("description", ""),
                required_tool_combination=approval.get("tools", []),
                estimated_success_rate=0.6,
                risk_level="高",
                innovation_basis="人工审核通过"
            )
            if self._publish_innovation_plan:
                self._publish_innovation_plan(plan)
            self._plans_created += 1

    # ========== 辅助 ==========
    def _check_resources(self) -> bool:
        if self._query_resource_status:
            status = self._query_resource_status()
            if status:
                cpu = status.get("cpu_usage_pct", 0)
                mem = status.get("memory_usage_pct", 0)
                return cpu < self.MAX_CPU_USAGE_PCT and mem < self.MAX_MEMORY_USAGE_PCT
        return True

    def _publish_status(self):
        if self._publish_status_report:
            self._publish_status_report(CreationStatus(
                state=self.state,
                processed_experiences=self._processed_experiences,
                rules_generated=self._rules_generated,
                plans_created=self._plans_created,
                resource_consumption=0.0
            ))

    def get_state(self) -> CreationState:
        return self.state

    def emergency_shutdown(self):
        self.state = CreationState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 抽象创造模块 (ag-ecc-11) 演示")
    print("=" * 70)

    creator = AbstractCreation()

    print_separator("STEP 1: 触发抽象提炼（含工具序列挖掘）")
    creator.set_experience_data_query(lambda domain, count: ExperienceData(
        domain="工具调用",
        entries=[
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["search_engine", "parse_html"], "result_label": "失败", "error_code": "TIMEOUT", "task_steps": ["搜索", "解析"]},
            {"tool_call_sequence": ["search_engine", "parse_html"], "result_label": "失败", "error_code": "TIMEOUT", "task_steps": ["搜索", "解析"]},
            {"tool_call_sequence": ["search_engine", "parse_html"], "result_label": "失败", "error_code": "TIMEOUT", "task_steps": ["搜索", "解析"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
            {"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]},
        ],
        total_count=20
    ))
    creator.set_abstraction_trigger_query(lambda: AbstractionTrigger(
        trigger_type="经验累积", target_domain="工具调用", min_experience_count=20
    ))
    creator.run_creation_cycle()
    print(f"  生成规则数: {creator._rules_generated}")

    print_separator("STEP 2: 创新探索（低风险自动执行）")
    creator.set_innovation_drive_query(lambda: InnovationDrive(
        direction="新工具组合", available_tools=["weather_api", "format_result"],
        goal_description="测试weather_api+format_result组合"
    ))
    creator.run_creation_cycle()
    print(f"  创建方案数: {creator._plans_created}")

    print("\n✅ 抽象创造模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-11 抽象创造模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_creator():
            return AbstractCreation()

        # TC-E11-01: 经验累积触发多维规则生成
        print("\n[TC-E11-01] 经验累积触发多维规则生成")
        try:
            c = setup_creator()
            entries = []
            for _ in range(15):
                entries.append({"tool_call_sequence": ["weather_api", "format_result"], "result_label": "成功", "task_steps": ["查询", "格式化"]})
            for _ in range(5):
                entries.append({"tool_call_sequence": ["search_engine", "parse_html"], "result_label": "失败", "error_code": "TIMEOUT", "task_steps": ["搜索", "解析"]})
            c.set_experience_data_query(lambda domain, count: ExperienceData(
                domain="工具调用", entries=entries, total_count=20
            ))
            c.set_abstraction_trigger_query(lambda: AbstractionTrigger(
                trigger_type="经验累积", target_domain="工具调用", min_experience_count=20
            ))
            c.run_creation_cycle()
            assert c._rules_generated >= 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E11-02: 经验不足放弃提炼
        print("\n[TC-E11-02] 经验不足放弃提炼")
        try:
            c = setup_creator()
            c.set_experience_data_query(lambda domain, count: ExperienceData(
                domain=domain, entries=[], total_count=5
            ))
            c.set_abstraction_trigger_query(lambda: AbstractionTrigger(
                trigger_type="经验累积", target_domain="测试", min_experience_count=20
            ))
            c.run_creation_cycle()
            assert c._rules_generated == 0
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E11-03: 低风险创新方案自动创建
        print("\n[TC-E11-03] 低风险创新方案自动创建")
        try:
            c = setup_creator()
            c.set_innovation_drive_query(lambda: InnovationDrive(
                direction="测试", available_tools=["tool_a", "tool_b"],
                goal_description="测试组合"
            ))
            c.run_creation_cycle()
            assert c._plans_created == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E11-04: 高风险方案进入人工审核
        print("\n[TC-E11-04] 高风险方案进入人工审核")
        try:
            c = setup_creator()
            c.set_capability_boundary_query(lambda: CapabilityBoundary(
                known_infeasible_solutions=["tool_x+tool_y"]
            ))
            c.set_innovation_drive_query(lambda: InnovationDrive(
                direction="高危", available_tools=["delete_file", "shell_exec", "system_config"],
                goal_description="高危测试"
            ))
            c.run_creation_cycle()
            assert c.state == CreationState.AWAITING_APPROVAL
            assert c._plans_created == 0
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E11-05: 人工审核批准
        print("\n[TC-E11-05] 人工审核批准")
        try:
            c = setup_creator()
            c.state = CreationState.AWAITING_APPROVAL
            c.set_manual_approval_query(lambda: {"result": "approve", "creation_id": "T05", "description": "test", "tools": ["a", "b"]})
            c.run_creation_cycle()
            assert c._plans_created == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E11-06: 紧急熔断
        print("\n[TC-E11-06] 紧急熔断")
        try:
            c = setup_creator()
            c.emergency_shutdown()
            assert c.state == CreationState.SYSTEM_PAUSED
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