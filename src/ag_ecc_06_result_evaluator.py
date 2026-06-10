#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-06
名称: 结果评估模块
版本：V1.0（最终审查通过版）
修复：仅增加 ag-ecc-12.pause 监听，业务逻辑完全不变
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-06")

# ==================== 状态枚举（按审查建议改为大写，不影响功能）====================
class EvaluatorState(Enum):
    WAITING_RESULT        = "WAITING_RESULT"
    EVALUATING           = "EVALUATING"
    ANOMALY_ANALYSIS     = "ANOMALY_ANALYSIS"
    EXPERIENCE_WRITING   = "EXPERIENCE_WRITING"
    SYSTEM_PAUSED        = "SYSTEM_PAUSED"

class AnomalyType(Enum):
    TEMPORARY            = "临时性错误"
    PARAM_ERROR          = "参数错误"
    PERMISSION_DENIED    = "权限不足"
    TOOL_UNAVAILABLE     = "工具不可用"
    UNKNOWN              = "未知错误"

class EvaluationConclusion(Enum):
    SUCCESS              = "成功"
    SUCCESS_WITH_DEVIATION = "成功但有偏差"
    RETRY_NEEDED         = "需重试"
    FAILURE_UNRECOVERABLE = "失败不可恢复"

@dataclass
class ToolExecutionResult:
    step_id: str = ""
    plan_id: str = ""
    tool_name: str = ""
    status: str = "success"
    output_data: Dict[str, Any] = field(default_factory=dict)
    duration_sec: float = 0.0
    error_code: str = ""
    error_message: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolExecutionResult":
        try:
            fields = set(cls.__dataclass_fields__.keys())
            return cls(**{k: v for k, v in data.items() if k in fields})
        except Exception:
            return cls()

@dataclass
class ExpectedResult:
    step_id: str = ""
    expected_output_format: Dict[str, Any] = field(default_factory=dict)
    acceptable_deviation: float = 0.2
    key_fields: List[str] = field(default_factory=list)
    estimated_duration_sec: float = 30.0

@dataclass
class EvaluationResult:
    step_id: str = ""
    plan_id: str = ""
    conclusion: EvaluationConclusion = EvaluationConclusion.SUCCESS
    deviation_description: str = ""
    suggested_action: str = ""
    anomaly_type: Optional[AnomalyType] = None
    quality_scores: Dict[str, float] = field(default_factory=dict)
    evaluation_duration_ms: float = 0.0

class ResultEvaluator:
    FORMAT_MATCH_WEIGHT = 0.40
    DURATION_REASONABLE_WEIGHT = 0.25
    COMPLETENESS_WEIGHT = 0.20
    ANOMALY_SIGNAL_WEIGHT = 0.15

    MAX_CONSECUTIVE_RETRIES = 3
    STATUS_REPORT_INTERVAL_SEC = 60
    QUERY_EXPECTED_TIMEOUT = 0.5

    TEMPORARY_ERROR_CODES = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED", "CONNECTION_REFUSED"}
    PARAM_ERROR_CODES = {"INVALID_PARAM", "MISSING_PARAM", "PARAM_TYPE_ERROR"}
    PERMISSION_ERROR_CODES = {"PERMISSION_DENIED", "UNAUTHORIZED", "FORBIDDEN"}
    TOOL_UNAVAILABLE_CODES = {"SERVICE_UNAVAILABLE", "TOOL_OFFLINE", "MAINTENANCE"}

    def __init__(self):
        self.module_id = "ag-ecc-06"
        self.version = "V1.0"
        self.state = EvaluatorState.WAITING_RESULT
        self.bus = None

        self._retry_counters = {}
        self._total_evaluations = 0
        self._success_count = 0
        self._total_evaluation_time = 0.0
        self._last_status_time = time.time()

        self._result_buffer = []
        self._expected_cache = {}

        logger.info("✅ ag-ecc-06 初始化完成")

    def handle_message(self, msg: Message):
        try:
            topic = msg.topic

            if topic == "ag-ecc-06.execution_result":
                res = ToolExecutionResult.from_dict(msg.data)
                self._result_buffer.append(res)

            elif topic == "ag-ecc-06.expected_result":
                exp = ExpectedResult(**msg.data)
                self._expected_cache[exp.step_id] = exp

            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-06.shutdown"):
                self.emergency_shutdown()

            # ==================== 修复：这里只加了 1 行 ====================
            elif topic == "ag-ecc-12.pause":
                self.emergency_shutdown()

            elif topic == "ag-ecc-12.resume":
                if self.state == EvaluatorState.SYSTEM_PAUSED:
                    self.state = EvaluatorState.WAITING_RESULT
                    logger.info("▶️ 模块已恢复")

        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    def result_evaluator_main_loop(self):
        if self.state == EvaluatorState.SYSTEM_PAUSED:
            return

        now = time.time()
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        while self._result_buffer and self.state == EvaluatorState.WAITING_RESULT:
            self._process_single_result(self._result_buffer.pop(0))

    def _process_single_result(self, result: ToolExecutionResult):
        self.state = EvaluatorState.EVALUATING
        start = time.time()

        expected = self._expected_cache.pop(result.step_id, None)
        if not expected:
            expected = self._fetch_expected_result(result)

        eval_res = self._evaluate(result, expected)
        elapsed = time.time() - start
        eval_res.evaluation_duration_ms = round(elapsed * 1000, 2)

        self._total_evaluation_time += elapsed
        self._total_evaluations += 1

        if eval_res.conclusion == EvaluationConclusion.SUCCESS:
            self._success_count += 1
            self._retry_counters.pop(result.step_id, None)

        self._notify_task_planner(result, eval_res)
        self._persist_experience(result, eval_res)

        self.state = EvaluatorState.WAITING_RESULT

    def _fetch_expected_result(self, result: ToolExecutionResult) -> Optional[ExpectedResult]:
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic="ag-ecc-02.query_expected_result",
                source_module=self.module_id,
                target_module="ag-ecc-02",
                data={"step_id": result.step_id, "plan_id": result.plan_id},
                timeout_ms=500
            )
            if resp and resp.data:
                return ExpectedResult(**resp.data)
        except Exception:
            return None

    def _evaluate(self, result: ToolExecutionResult, expected: Optional[ExpectedResult]) -> EvaluationResult:
        if result.status in ("failure", "timeout", "exception"):
            self.state = EvaluatorState.ANOMALY_ANALYSIS
            return self._analyze_anomaly(result)

        if not expected:
            return EvaluationResult(step_id=result.step_id, plan_id=result.plan_id)

        scores = {
            "format_match": self._score_format(result.output_data, expected.expected_output_format),
            "duration_reasonable": self._score_duration(result.duration_sec, expected.estimated_duration_sec),
            "completeness": self._score_completeness(result.output_data, expected.key_fields),
            "anomaly_free": 1.0
        }

        overall = (
            self.FORMAT_MATCH_WEIGHT * scores["format_match"] +
            self.DURATION_REASONABLE_WEIGHT * scores["duration_reasonable"] +
            self.COMPLETENESS_WEIGHT * scores["completeness"] +
            self.ANOMALY_SIGNAL_WEIGHT * scores["anomaly_free"]
        )

        conclusion = EvaluationConclusion.SUCCESS if overall >= 0.7 else EvaluationConclusion.SUCCESS_WITH_DEVIATION

        return EvaluationResult(
            step_id=result.step_id,
            plan_id=result.plan_id,
            conclusion=conclusion,
            deviation_description="" if overall >= 0.7 else "输出与预期存在偏差",
            quality_scores=scores
        )

    def _analyze_anomaly(self, result: ToolExecutionResult) -> EvaluationResult:
        code = result.error_code
        if code in self.TEMPORARY_ERROR_CODES:
            t = AnomalyType.TEMPORARY
            c = EvaluationConclusion.RETRY_NEEDED
            act = "自动重试"
        elif code in self.PARAM_ERROR_CODES:
            t = AnomalyType.PARAM_ERROR
            c = EvaluationConclusion.FAILURE_UNRECOVERABLE
            act = "修正参数后重试"
        elif code in self.PERMISSION_ERROR_CODES:
            t = AnomalyType.PERMISSION_DENIED
            c = EvaluationConclusion.FAILURE_UNRECOVERABLE
            act = "需用户授权"
        elif code in self.TOOL_UNAVAILABLE_CODES:
            t = AnomalyType.TOOL_UNAVAILABLE
            c = EvaluationConclusion.RETRY_NEEDED
            act = "切换备选工具"
        else:
            t = AnomalyType.UNKNOWN
            c = EvaluationConclusion.FAILURE_UNRECOVERABLE
            act = "人工介入"

        return EvaluationResult(
            step_id=result.step_id,
            plan_id=result.plan_id,
            conclusion=c,
            deviation_description=f"{t.value}: {code}",
            suggested_action=act,
            anomaly_type=t
        )

    def _notify_task_planner(self, result: ToolExecutionResult, eval_res: EvaluationResult):
        if eval_res.conclusion == EvaluationConclusion.RETRY_NEEDED:
            cnt = self._retry_counters.get(result.step_id, 0) + 1
            self._retry_counters[result.step_id] = cnt
            if cnt >= self.MAX_CONSECUTIVE_RETRIES:
                eval_res.conclusion = EvaluationConclusion.FAILURE_UNRECOVERABLE
                eval_res.suggested_action = f"连续重试{self.MAX_CONSECUTIVE_RETRIES}次失败"

        if not self.bus:
            return

        if eval_res.conclusion == EvaluationConclusion.FAILURE_UNRECOVERABLE:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="step_failure",
                source_module=self.module_id,
                data={
                    "plan_id": result.plan_id,
                    "failed_step_id": result.step_id,
                    "anomaly_type": eval_res.anomaly_type.value if eval_res.anomaly_type else "UNKNOWN",
                    "failure_reason": eval_res.deviation_description,
                    "recovery_suggestion": eval_res.suggested_action,
                },
                priority=PRIORITY_HIGH
            )
        else:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="step_completed",
                source_module=self.module_id,
                data={
                    "plan_id": result.plan_id,
                    "step_id": result.step_id,
                    "conclusion": eval_res.conclusion.value,
                    "deviation_description": eval_res.deviation_description,
                    "suggested_action": eval_res.suggested_action
                },
                priority=PRIORITY_NORMAL
            )

    def _persist_experience(self, result: ToolExecutionResult, eval_res: EvaluationResult):
        if not self.bus:
            return
        self.state = EvaluatorState.EXPERIENCE_WRITING

        if result.status == "failure":
            label, imp = "失败", 0.7
        elif result.status == "success" and result.duration_sec > 30:
            label, imp = "成功优化", 0.6
        else:
            return

        self.bus.publish_to_module(
            target_module="ag-ecc-05",
            event_type="write_experience",
            source_module=self.module_id,
            data={
                "entry_id": f"EXP-{uuid.uuid4().hex[:8]}",
                "experience_type": label,
                "scene_label": "工具调用",
                "task_description": f"执行工具: {result.tool_name}",
                "tool_sequence": [result.tool_name],
                "result_label": label,
                "estimated_importance": imp,
            },
            priority=PRIORITY_NORMAL
        )

    def _score_format(self, out, exp):
        if not exp or not out:
            return 0.0
        ek, ok = set(exp.keys()), set(out.keys())
        return len(ek & ok) / len(ek) if ek else 1.0

    def _score_duration(self, actual, est):
        if est <= 0:
            return 1.0
        r = actual / est
        if r <= 1:
            return 1.0
        if r <= 2:
            return 1.0 - 0.5 * (r - 1)
        return 0.3

    def _score_completeness(self, out, fields):
        if not fields or not out:
            return 0.0
        ok = sum(1 for f in fields if f in out and out[f] is not None)
        return ok / len(fields)

    def _publish_status(self):
        if not self.bus:
            return
        avg = self._total_evaluation_time / max(self._total_evaluations, 1)
        rate = self._success_count / max(self._total_evaluations, 1)
        self.bus.publish_to_module(
            target_module="ag-ecc-12",
            event_type="evaluator_status",
            source_module=self.module_id,
            data={
                "state": self.state.value,
                "total_evaluations": self._total_evaluations,
                "success_rate": round(rate, 3),
                "avg_duration_ms": round(avg * 1000, 2),
            },
            priority=PRIORITY_NORMAL
        )

    def emergency_shutdown(self):
        self.state = EvaluatorState.SYSTEM_PAUSED
        logger.info("⏹️ 模块已暂停")

    def get_state(self):
        return self.state