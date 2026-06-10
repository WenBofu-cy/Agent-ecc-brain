#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-08
模块名称: 元认知模块
所属分区: 一、认知大脑核心模块
核心职责: 自我觉察与自省中枢，监控运行状态、认知能力、决策质量，输出能力评估报告，
          检测认知偏差并触发学习需求，必要时向用户或大模型发起求助。
          不参与具体任务推理或执行，仅负责“对认知过程本身的认知”。

依赖模块: ag-ecc-05, ag-ecc-06, ag-ecc-07, ag-ecc-12
被依赖模块: ag-ecc-02, ag-ecc-09, ag-ecc-12

安全约束:
  M-01: 仅做监控与建议输出，不直接干预业务模块运行或决策
  M-02: 系统能力评估报告仅保留最近90天趋势数据，超期自动清除
  M-03: 主动求助时，发送给大模型的困境描述须经过去个性化处理
  M-04: 求助冷却机制确保不会短时间内频繁发起重复求助
  M-05: 元认知运行日志不得包含任何可关联到特定用户的身份信息
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-08")


# ==================== 状态枚举：大写合规（CPEC 标准）====================
class MetacognitionState(Enum):
    NORMAL_MONITOR = "NORMAL_MONITOR"
    ANOMALY_ATTENTION = "ANOMALY_ATTENTION"
    CAPABILITY_ASSESSING = "CAPABILITY_ASSESSING"
    GAP_IDENTIFYING = "GAP_IDENTIFYING"
    HELP_SEEKING = "HELP_SEEKING"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"


class BiasType(Enum):
    OVERCONFIDENCE = "过度自信"
    OVERCAUTIOUS = "过度保守"
    EXPERIENCE_DEPENDENCY = "经验依赖"
    CAPABILITY_MISJUDGMENT = "能力误判"


@dataclass
class SystemMetrics:
    task_success_rate: float = 0.9
    avg_response_ms: float = 500.0
    anomaly_rate: float = 0.02
    tool_call_failure_rate: float = 0.05
    intent_accuracy: float = 0.85
    disambiguation_rate: float = 0.0
    user_direct_execute_ratio: float = 0.0
    template_reliance_rate: float = 0.0
    new_tool_adoption_rate: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemMetrics":
        try:
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except:
            return cls()


@dataclass
class FailureExperienceEntry:
    entry_id: str = ""
    failure_reason: str = ""
    failure_category: str = ""
    arbitration_passed: bool = False


@dataclass
class CapabilityReport:
    assessment_time: float = field(default_factory=time.time)
    capability_scores: Dict[str, float] = field(default_factory=dict)
    weaknesses: List[Dict[str, Any]] = field(default_factory=list)
    trend: str = "稳定"
    improvement_suggestions: List[str] = field(default_factory=list)


@dataclass
class CognitiveBiasAlert:
    bias_type: BiasType = BiasType.OVERCONFIDENCE
    involved_module: str = ""
    severity: str = "中"
    suggested_correction: str = ""


@dataclass
class LearningRequirement:
    gap_description: str = ""
    target_dimension: str = ""
    suggested_method: str = "内部复盘"
    priority: float = 0.5


@dataclass
class HelpRequest:
    help_id: str = ""
    dilemma_description: str = ""
    attempted_solutions: List[str] = field(default_factory=list)
    help_type: str = "用户确认"
    timeout_sec: int = 60


class MetacognitionModule:
    HEALTH_THRESHOLDS = {
        "intent_understanding": 0.85,
        "task_planning": 0.80,
        "tool_usage": 0.90,
        "safety_compliance": 0.95,
        "memory_retrieval": 0.70,
        "overall_quality": 0.80,
    }
    HELP_COOLDOWN_SEC = 3600
    ASSESSMENT_INTERVAL_SEC = 86400
    CONSECUTIVE_ANOMALY_THRESHOLD = 3
    STATUS_REPORT_INTERVAL_SEC = 120

    OVERCAUTIOUS_DISAMBIGUATION_RATE = 0.3
    OVERCAUTIOUS_DIRECT_EXEC_RATIO = 0.6
    EXPERIENCE_TEMPLATE_RELIANCE = 0.8
    EXPERIENCE_NEW_TOOL_ADOPTION = 0.2

    def __init__(self):
        self.module_id = "ag-ecc-08"
        self.version = "V1.0"
        self.state = MetacognitionState.NORMAL_MONITOR
        self.bus = None

        self._capability_scores: Dict[str, float] = {k: 1.0 for k in self.HEALTH_THRESHOLDS}
        self._anomaly_counter: int = 0
        self._last_assessment_time: float = 0.0
        self._last_help_time: float = 0.0
        self._help_count: int = 0
        self._last_status_time: float = time.time()

        self._metrics_buffer: List[SystemMetrics] = []
        self._failure_buffer: List[FailureExperienceEntry] = []
        self._assessment_trigger: bool = False
        self._help_responses: List[Dict[str, Any]] = []
        self._llm_responses: List[Dict[str, Any]] = []

        self._trend_history: List[Dict[str, Any]] = []

        logger.info("✅ 元认知模块初始化完成")

    # ====================== 总线消息入口 ======================
    def handle_message(self, msg: Message):
        try:
            topic = msg.topic

            if topic == "ag-ecc-08.metrics":
                self._metrics_buffer.append(SystemMetrics.from_dict(msg.data))

            elif topic == "ag-ecc-08.failure_experience":
                try:
                    entries = [FailureExperienceEntry(**e) for e in msg.data.get("entries", [])]
                    self._failure_buffer.extend(entries)
                except:
                    pass

            elif topic == "ag-ecc-08.assess_trigger":
                self._assessment_trigger = True

            elif topic == "ag-ecc-08.help_response":
                self._help_responses.append(msg.data)

            elif topic == "ag-ecc-08.llm_response":
                self._llm_responses.append(msg.data)

            # ==================== 修复：全局暂停 / 关闭 ====================
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-08.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()

            elif topic == "ag-ecc-12.resume":
                if self.state == MetacognitionState.SYSTEM_PAUSED:
                    self.state = MetacognitionState.NORMAL_MONITOR
                    logger.info("▶️ 元认知模块已恢复服务")

        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    # ====================== CPEC 主循环 ======================
    def metacognition_main_loop(self):
        if self.state == MetacognitionState.SYSTEM_PAUSED:
            return

        now = time.time()

        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        self._process_help_responses(now)
        self._process_llm_responses(now)

        metrics = self._metrics_buffer.pop(0) if self._metrics_buffer else None
        if metrics:
            self._monitor_anomalies(metrics, now)

        if self._assessment_trigger or (now - self._last_assessment_time >= self.ASSESSMENT_INTERVAL_SEC):
            self._perform_capability_assessment(now)
            self._assessment_trigger = False

    # ====================== 求助响应处理 ======================
    def _process_help_responses(self, now: float):
        while self._help_responses:
            resp = self._help_responses.pop(0)
            try:
                if resp.get("accepted", False):
                    self._anomaly_counter = max(0, self._anomaly_counter - 1)
            except:
                pass

    def _process_llm_responses(self, now: float):
        while self._llm_responses:
            resp = self._llm_responses.pop(0)
            try:
                suggestion = resp.get("suggestion", "")
                if suggestion:
                    req = LearningRequirement(
                        gap_description=f"大模型建议: {suggestion[:200]}",
                        target_dimension="大模型辅助",
                        suggested_method="外部知识获取",
                        priority=0.8
                    )
                    self._publish_learning_requirement(req)
            except:
                pass

    # ====================== 能力评估 ======================
    def _perform_capability_assessment(self, now: float):
        self.state = MetacognitionState.CAPABILITY_ASSESSING
        metrics = None

        if self.bus:
            try:
                resp = self.bus.request(
                    topic="ag-ecc-12.query_metrics",
                    source_module=self.module_id,
                    target_module="ag-ecc-12",
                    data={},
                    timeout_ms=1000
                )
                if resp and resp.data:
                    metrics = SystemMetrics.from_dict(resp.data)
            except:
                pass

        failures = self._failure_buffer.copy()
        scores = self._capability_scores.copy()

        if metrics:
            try:
                scores["intent_understanding"] = metrics.intent_accuracy
                scores["task_planning"] = metrics.task_success_rate
                scores["tool_usage"] = 1.0 - metrics.tool_call_failure_rate
                scores["safety_compliance"] = max(0.0, 1.0 - metrics.anomaly_rate * 5)
                scores["memory_retrieval"] = 0.75
                total = sum(scores.values())
                count = max(len(scores), 1)
                scores["overall_quality"] = total / count
            except:
                pass

        self._capability_scores = scores

        self._trend_history.append({"time": now, "scores": scores.copy()})
        cutoff = now - 90 * 86400
        self._trend_history = [e for e in self._trend_history if e["time"] >= cutoff]

        weaknesses = []
        for dim, threshold in self.HEALTH_THRESHOLDS.items():
            current = scores.get(dim, 1.0)
            if current < threshold:
                weaknesses.append({
                    "dimension": dim,
                    "score": round(current, 2),
                    "gap": round(threshold - current, 2)
                })

        report = CapabilityReport(
            assessment_time=now,
            capability_scores=scores,
            weaknesses=weaknesses,
            trend="下降" if weaknesses else "稳定",
            improvement_suggestions=[f"建议提升{w['dimension']}能力" for w in weaknesses]
        )
        self._publish_report(report)

        if weaknesses:
            self.state = MetacognitionState.GAP_IDENTIFYING
            for w in weaknesses:
                req = LearningRequirement(
                    gap_description=f"{w['dimension']}评分{w['score']}低于阈值{self.HEALTH_THRESHOLDS[w['dimension']]}",
                    target_dimension=w['dimension'],
                    suggested_method="内部复盘",
                    priority=min(1.0, w['gap'] * 10)
                )
                self._publish_learning_requirement(req)

        self._last_assessment_time = now
        self.state = MetacognitionState.NORMAL_MONITOR

    # ====================== 异常监控 ======================
    def _monitor_anomalies(self, metrics: SystemMetrics, now: float):
        try:
            is_anomalous = (
                metrics.task_success_rate < 0.6 or
                metrics.tool_call_failure_rate > 0.3 or
                metrics.anomaly_rate > 0.1
            )
        except:
            is_anomalous = False

        if is_anomalous:
            self.state = MetacognitionState.ANOMALY_ATTENTION
            self._anomaly_counter += 1

            bias = self._detect_cognitive_bias(metrics)
            if bias:
                self._publish_bias_alert(bias)

            if self._anomaly_counter >= self.CONSECUTIVE_ANOMALY_THRESHOLD:
                if now - self._last_help_time >= self.HELP_COOLDOWN_SEC:
                    self.state = MetacognitionState.HELP_SEEKING
                    desc = f"系统连续{self._anomaly_counter}次异常 | 任务成功率={metrics.task_success_rate:.2f}"
                    help_req = HelpRequest(
                        help_id=f"HLP-{uuid.uuid4().hex[:8]}",
                        dilemma_description=desc,
                        attempted_solutions=["内部监控", "能力评估"],
                        help_type="用户确认",
                        timeout_sec=60
                    )
                    self._publish_help_request(help_req)
                    self._last_help_time = now
                    self._help_count += 1

            self.state = MetacognitionState.NORMAL_MONITOR
        else:
            if self._anomaly_counter > 0:
                self._anomaly_counter = max(0, self._anomaly_counter - 1)

    def _detect_cognitive_bias(self, metrics: SystemMetrics) -> Optional[CognitiveBiasAlert]:
        try:
            if metrics.task_success_rate < 0.7 and metrics.intent_accuracy > 0.9:
                return CognitiveBiasAlert(BiasType.OVERCONFIDENCE, "ag-ecc-01", "中", "降低置信度预测比例")
            if (metrics.disambiguation_rate > self.OVERCAUTIOUS_DISAMBIGUATION_RATE and
                metrics.user_direct_execute_ratio > self.OVERCAUTIOUS_DIRECT_EXEC_RATIO):
                return CognitiveBiasAlert(BiasType.OVERCAUTIOUS, "ag-ecc-01", "低", "减少不必要消歧")
            if (metrics.template_reliance_rate > self.EXPERIENCE_TEMPLATE_RELIANCE and
                metrics.new_tool_adoption_rate < self.EXPERIENCE_NEW_TOOL_ADOPTION):
                return CognitiveBiasAlert(BiasType.EXPERIENCE_DEPENDENCY, "ag-ecc-03", "中", "增加新工具探索")
            if metrics.tool_call_failure_rate > 0.3:
                return CognitiveBiasAlert(BiasType.CAPABILITY_MISJUDGMENT, "ag-ecc-03", "高", "重新评估工具策略")
        except:
            return None
        return None

    # ====================== 发布方法（总线） ======================
    def _publish_report(self, report: CapabilityReport):
        if self.bus:
            try:
                self.bus.publish_to_module(
                    target_module="ag-ecc-12",
                    event_type="capability_report",
                    source_module=self.module_id,
                    data=report.__dict__,
                    priority=PRIORITY_LOW
                )
            except:
                pass

    def _publish_bias_alert(self, alert: CognitiveBiasAlert):
        if self.bus:
            try:
                data = {
                    "bias_type": alert.bias_type.value,
                    "involved_module": alert.involved_module,
                    "severity": alert.severity,
                    "suggested_correction": alert.suggested_correction
                }
                self.bus.publish_to_module("ag-ecc-09", "bias_alert", self.module_id, data, PRIORITY_HIGH)
                self.bus.publish_to_module("ag-ecc-12", "bias_alert", self.module_id, data, PRIORITY_NORMAL)
            except:
                pass

    def _publish_learning_requirement(self, req: LearningRequirement):
        if self.bus:
            try:
                self.bus.publish_to_module(
                    target_module="ag-ecc-09",
                    event_type="learning_requirement",
                    source_module=self.module_id,
                    data=req.__dict__,
                    priority=PRIORITY_NORMAL
                )
            except:
                pass

    def _publish_help_request(self, req: HelpRequest):
        if self.bus:
            try:
                self.bus.publish_to_module(
                    target_module="ag-ecc-12",
                    event_type="help_request",
                    source_module=self.module_id,
                    data=req.__dict__,
                    priority=PRIORITY_HIGH
                )
            except:
                pass

    def _publish_status(self):
        if self.bus:
            try:
                status_data = {
                    "state": self.state.value,
                    "anomaly_count_recent": self._anomaly_counter,
                    "last_assessment_time": self._last_assessment_time,
                    "capability_score_trend": "下降" if self._anomaly_counter > 0 else "稳定",
                    "help_request_count": self._help_count,
                }
                self.bus.publish_to_module(
                    target_module="ag-ecc-12",
                    event_type="metacognition_status",
                    source_module=self.module_id,
                    data=status_data,
                    priority=PRIORITY_LOW
                )
            except:
                pass

    # ====================== 辅助 ======================
    def emergency_shutdown(self):
        self.state = MetacognitionState.SYSTEM_PAUSED
        logger.info("⏹️ 元认知模块已暂停（系统熔断）")

    def get_state(self) -> MetacognitionState:
        return self.state