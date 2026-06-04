#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-06
模块名称: 结果评估模块
所属分区: 一、认知大脑核心模块
核心职责: 接收行动执行层（Agent-mcc-exec）返回的工具调用结果或任务步骤完成回执，对执行
          结果进行质量评估、完成度判定与异常识别。将评估后的结果反馈给 ag-ecc-02（任务
          规划模块）用于进度跟踪与异常恢复决策，同时将具有学习价值的成功/失败经验片段
          通过 ag-ecc-05（记忆查询模块）写入 MLNF-Mem 记忆中枢。不参与任务规划或工具
          执行，仅负责执行结果的客观评估与经验沉淀触发。

依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-05(记忆查询模块), ag-mcc-exec(行动执行层)
被依赖模块:
    ag-ecc-02, ag-ecc-08(元认知模块，可选提供评估数据)

安全约束:
  E-01: 本模块仅评估执行结果，不参与任务规划、工具选择或安全仲裁决策
  E-02: 写入记忆中枢的经验条目必须经过去个性化处理，不得包含用户的原始输入数据
  E-03: 评估过程中使用的预期结果定义不得包含任何敏感信息
  E-04: 评估结论仅作为建议输出，任务规划模块有权根据全局态势进行最终决策
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class EvaluatorState(Enum):
    WAITING_RESULT = "waiting_result"
    EVALUATING = "evaluating"
    ANOMALY_ANALYSIS = "anomaly_analysis"
    EXPERIENCE_WRITING = "experience_writing"
    SYSTEM_PAUSED = "system_paused"


class ExecutionStatus(Enum):
    SUCCESS = "成功"
    FAILURE = "失败"
    TIMEOUT = "超时"
    EXCEPTION = "异常"


class AnomalyType(Enum):
    TEMPORARY = "临时性错误"
    PARAM_ERROR = "参数错误"
    PERMISSION_DENIED = "权限不足"
    TOOL_UNAVAILABLE = "工具不可用"
    UNKNOWN = "未知错误"


class EvaluationConclusion(Enum):
    SUCCESS = "成功"
    SUCCESS_WITH_DEVIATION = "成功但有偏差"
    RETRY_NEEDED = "需重试"
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
    timestamp: float = field(default_factory=time.time)


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


@dataclass
class StepCompletionNotice:
    plan_id: str = ""
    step_id: str = ""
    conclusion: EvaluationConclusion = EvaluationConclusion.SUCCESS
    deviation_description: str = ""
    suggested_action: str = ""


@dataclass
class AnomalyInterruptNotice:
    plan_id: str = ""
    failed_step_id: str = ""
    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    failure_reason: str = ""
    recovery_suggestion: str = ""
    completed_progress: float = 0.0


@dataclass
class ExperienceWriteRequest:
    entry_id: str = ""
    experience_type: str = ""
    scene_label: str = ""
    task_description: str = ""
    tool_sequence: List[str] = field(default_factory=list)
    result_label: str = ""
    estimated_importance: float = 0.5
    timestamp: float = field(default_factory=time.time)


@dataclass
class EvaluatorStatus:
    state: EvaluatorState = EvaluatorState.WAITING_RESULT
    total_evaluations: int = 0
    success_rate: float = 0.0
    avg_evaluation_ms: float = 0.0


class ResultEvaluator:
    # 评估权重
    FORMAT_MATCH_WEIGHT = 0.40
    DURATION_REASONABLE_WEIGHT = 0.25
    COMPLETENESS_WEIGHT = 0.20
    ANOMALY_SIGNAL_WEIGHT = 0.15

    # 重试配置
    MAX_CONSECUTIVE_RETRIES = 3
    STATUS_REPORT_INTERVAL_SEC = 60

    # 异常分类映射
    TEMPORARY_ERROR_CODES = {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED", "CONNECTION_REFUSED"}
    PARAM_ERROR_CODES = {"INVALID_PARAM", "MISSING_PARAM", "PARAM_TYPE_ERROR"}
    PERMISSION_ERROR_CODES = {"PERMISSION_DENIED", "UNAUTHORIZED", "FORBIDDEN"}
    TOOL_UNAVAILABLE_CODES = {"SERVICE_UNAVAILABLE", "TOOL_OFFLINE", "MAINTENANCE"}

    def __init__(self):
        self.module_id = "ag-ecc-06"
        self.module_name = "结果评估模块"
        self.version = "V1.0"

        self.state = EvaluatorState.WAITING_RESULT
        self._retry_counters: Dict[str, int] = {}  # step_id -> 连续重试次数
        self._total_evaluations: int = 0
        self._success_count: int = 0
        self._total_evaluation_time: float = 0.0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_execution_result = None
        self._query_expected_result = None

        self._publish_step_notice = None
        self._publish_anomaly_notice = None
        self._publish_experience_request = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_execution_result_query(self, callback: Callable[[], Optional[ToolExecutionResult]]):
        self._query_execution_result = callback

    def set_expected_result_query(self, callback: Callable[[str], Optional[ExpectedResult]]):
        self._query_expected_result = callback

    def set_step_notice_publisher(self, callback: Callable[[StepCompletionNotice], None]):
        self._publish_step_notice = callback

    def set_anomaly_notice_publisher(self, callback: Callable[[AnomalyInterruptNotice], None]):
        self._publish_anomaly_notice = callback

    def set_experience_request_publisher(self, callback: Callable[[ExperienceWriteRequest], None]):
        self._publish_experience_request = callback

    def set_status_report_publisher(self, callback: Callable[[EvaluatorStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_evaluation_cycle(self) -> Optional[EvaluationResult]:
        now = time.time()

        if self.state == EvaluatorState.SYSTEM_PAUSED:
            return None

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 接收执行结果
        result = self._query_execution_result() if self._query_execution_result else None
        if result is None:
            return None

        self.state = EvaluatorState.EVALUATING
        start_time = time.time()

        # 获取预期结果定义
        expected = self._query_expected_result(result.step_id) if self._query_expected_result else None

        # 评估
        evaluation = self._evaluate(result, expected)
        elapsed = (time.time() - start_time) * 1000
        evaluation.evaluation_duration_ms = elapsed

        self._total_evaluations += 1
        self._total_evaluation_time += elapsed

        # 统计成功率
        if evaluation.conclusion == EvaluationConclusion.SUCCESS:
            self._success_count += 1

        # 发送评估结果
        if evaluation.conclusion in (EvaluationConclusion.SUCCESS, EvaluationConclusion.SUCCESS_WITH_DEVIATION):
            self._send_step_notice(result, evaluation)
        elif evaluation.conclusion == EvaluationConclusion.RETRY_NEEDED:
            self._handle_retry(result, evaluation)
        else:
            self._send_anomaly_notice(result, evaluation)

        # 经验沉淀判定
        self._maybe_write_experience(result, evaluation)

        self.state = EvaluatorState.WAITING_RESULT
        return evaluation

    # ========== 核心评估 ==========
    def _evaluate(self, result: ToolExecutionResult, expected: Optional[ExpectedResult]) -> EvaluationResult:
        # 失败/超时直接进入异常分析
        if result.status in ("failure", "timeout", "exception"):
            self.state = EvaluatorState.ANOMALY_ANALYSIS
            anomaly_type = self._classify_anomaly(result.error_code)
            if anomaly_type == AnomalyType.TEMPORARY:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.RETRY_NEEDED,
                    deviation_description=f"临时性错误: {result.error_code}",
                    suggested_action="自动重试",
                    anomaly_type=anomaly_type
                )
            elif anomaly_type == AnomalyType.PARAM_ERROR:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.FAILURE_UNRECOVERABLE,
                    deviation_description=f"参数错误: {result.error_code}",
                    suggested_action="修正参数后重试",
                    anomaly_type=anomaly_type
                )
            elif anomaly_type == AnomalyType.PERMISSION_DENIED:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.FAILURE_UNRECOVERABLE,
                    deviation_description=f"权限不足: {result.error_code}",
                    suggested_action="需用户授权",
                    anomaly_type=anomaly_type
                )
            elif anomaly_type == AnomalyType.TOOL_UNAVAILABLE:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.RETRY_NEEDED,
                    deviation_description=f"工具不可用: {result.error_code}",
                    suggested_action="切换备选工具",
                    anomaly_type=anomaly_type
                )
            else:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.FAILURE_UNRECOVERABLE,
                    deviation_description=f"未知错误: {result.error_code}",
                    suggested_action="人工介入",
                    anomaly_type=AnomalyType.UNKNOWN
                )

        # 成功：计算质量评分
        scores = {}
        if expected:
            format_score = self._calculate_format_match(result.output_data, expected.expected_output_format)
            duration_score = self._calculate_duration_reasonable(result.duration_sec, expected.estimated_duration_sec)
            completeness_score = self._check_completeness(result.output_data, expected.key_fields)
            scores = {
                "format_match": format_score,
                "duration_reasonable": duration_score,
                "completeness": completeness_score,
                "anomaly_free": 1.0
            }
            overall = (
                self.FORMAT_MATCH_WEIGHT * format_score +
                self.DURATION_REASONABLE_WEIGHT * duration_score +
                self.COMPLETENESS_WEIGHT * completeness_score +
                self.ANOMALY_SIGNAL_WEIGHT * 1.0
            )
            if overall >= 0.7:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.SUCCESS,
                    quality_scores=scores
                )
            else:
                return EvaluationResult(
                    step_id=result.step_id, plan_id=result.plan_id,
                    conclusion=EvaluationConclusion.SUCCESS_WITH_DEVIATION,
                    deviation_description="输出与预期存在偏差",
                    quality_scores=scores
                )
        else:
            return EvaluationResult(
                step_id=result.step_id, plan_id=result.plan_id,
                conclusion=EvaluationConclusion.SUCCESS
            )

    def _classify_anomaly(self, error_code: str) -> AnomalyType:
        if error_code in self.TEMPORARY_ERROR_CODES:
            return AnomalyType.TEMPORARY
        elif error_code in self.PARAM_ERROR_CODES:
            return AnomalyType.PARAM_ERROR
        elif error_code in self.PERMISSION_ERROR_CODES:
            return AnomalyType.PERMISSION_DENIED
        elif error_code in self.TOOL_UNAVAILABLE_CODES:
            return AnomalyType.TOOL_UNAVAILABLE
        return AnomalyType.UNKNOWN

    # ========== 质量评分 ==========
    def _calculate_format_match(self, output: Dict, expected_format: Dict) -> float:
        if not expected_format:
            return 1.0
        if not output:
            return 0.0
        expected_keys = set(expected_format.keys())
        output_keys = set(output.keys())
        if not expected_keys:
            return 1.0
        overlap = len(expected_keys & output_keys)
        return round(overlap / len(expected_keys), 3)

    def _calculate_duration_reasonable(self, actual_sec: float, estimated_sec: float) -> float:
        if estimated_sec <= 0:
            return 1.0
        ratio = actual_sec / estimated_sec
        if ratio <= 1.0:
            return 1.0
        elif ratio <= 2.0:
            return round(1.0 - 0.5 * (ratio - 1.0), 3)
        else:
            return 0.3

    def _check_completeness(self, output: Dict, key_fields: List[str]) -> float:
        if not key_fields:
            return 1.0
        if not output:
            return 0.0
        present = sum(1 for f in key_fields if f in output and output[f] is not None)
        return round(present / len(key_fields), 3)

    # ========== 重试管理 ==========
    def _handle_retry(self, result: ToolExecutionResult, evaluation: EvaluationResult):
        step_id = result.step_id
        self._retry_counters[step_id] = self._retry_counters.get(step_id, 0) + 1

        if self._retry_counters[step_id] >= self.MAX_CONSECUTIVE_RETRIES:
            # 升级为失败不可恢复
            evaluation.conclusion = EvaluationConclusion.FAILURE_UNRECOVERABLE
            evaluation.suggested_action = f"连续重试{self.MAX_CONSECUTIVE_RETRIES}次均失败，需人工介入"
            self._retry_counters.pop(step_id, None)
            self._send_anomaly_notice(result, evaluation)
        else:
            self._send_step_notice(result, evaluation)

    # ========== 通知发送 ==========
    def _send_step_notice(self, result: ToolExecutionResult, evaluation: EvaluationResult):
        if self._publish_step_notice:
            self._publish_step_notice(StepCompletionNotice(
                plan_id=result.plan_id,
                step_id=result.step_id,
                conclusion=evaluation.conclusion,
                deviation_description=evaluation.deviation_description,
                suggested_action=evaluation.suggested_action
            ))

    def _send_anomaly_notice(self, result: ToolExecutionResult, evaluation: EvaluationResult):
        if self._publish_anomaly_notice:
            self._publish_anomaly_notice(AnomalyInterruptNotice(
                plan_id=result.plan_id,
                failed_step_id=result.step_id,
                anomaly_type=evaluation.anomaly_type or AnomalyType.UNKNOWN,
                failure_reason=evaluation.deviation_description,
                recovery_suggestion=evaluation.suggested_action
            ))

    # ========== 经验沉淀 ==========
    def _maybe_write_experience(self, result: ToolExecutionResult, evaluation: EvaluationResult):
        self.state = EvaluatorState.EXPERIENCE_WRITING

        # 失败经验必须记录
        if result.status == "failure":
            self._write_experience(result, "失败", 0.65)
        # 成功但耗时异常的经验也有学习价值
        elif result.duration_sec > 0 and result.status == "success":
            if result.duration_sec > 30.0:  # 耗时超过30秒
                self._write_experience(result, "成功优化", 0.55)

        self.state = EvaluatorState.WAITING_RESULT

    def _write_experience(self, result: ToolExecutionResult, label: str, importance: float):
        if self._publish_experience_request:
            # 去个性化处理：不包含用户原始输入
            self._publish_experience_request(ExperienceWriteRequest(
                entry_id=f"EXP-{uuid.uuid4().hex[:8]}",
                experience_type=label,
                scene_label="工具调用",
                task_description=f"执行工具: {result.tool_name}",
                tool_sequence=[result.tool_name],
                result_label=label,
                estimated_importance=importance
            ))

    # ========== 辅助 ==========
    def _publish_status(self):
        rate = self._success_count / max(self._total_evaluations, 1)
        avg = self._total_evaluation_time / max(self._total_evaluations, 1)
        if self._publish_status_report:
            self._publish_status_report(EvaluatorStatus(
                state=self.state,
                total_evaluations=self._total_evaluations,
                success_rate=round(rate, 3),
                avg_evaluation_ms=round(avg, 2)
            ))

    def get_state(self) -> EvaluatorState:
        return self.state

    def emergency_shutdown(self):
        self.state = EvaluatorState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 结果评估模块 (ag-ecc-06) 演示")
    print("=" * 70)

    evaluator = ResultEvaluator()

    print_separator("STEP 1: 评估成功结果")
    evaluator.set_execution_result_query(lambda: ToolExecutionResult(
        step_id="S01", plan_id="P01", tool_name="weather_api",
        status="success",
        output_data={"temperature": 25, "weather": "晴"},
        duration_sec=2.0
    ))
    result = evaluator.run_evaluation_cycle()
    if result:
        print(f"  结论: {result.conclusion.value}")

    print_separator("STEP 2: 评估失败结果（临时性错误）")
    evaluator.set_execution_result_query(lambda: ToolExecutionResult(
        step_id="S02", plan_id="P02", tool_name="search_engine",
        status="failure", error_code="TIMEOUT"
    ))
    result = evaluator.run_evaluation_cycle()
    if result:
        print(f"  结论: {result.conclusion.value}")
        print(f"  建议操作: {result.suggested_action}")

    print_separator("STEP 3: 评估失败结果（权限不足）")
    evaluator.set_execution_result_query(lambda: ToolExecutionResult(
        step_id="S03", plan_id="P03", tool_name="file_delete",
        status="failure", error_code="PERMISSION_DENIED"
    ))
    result = evaluator.run_evaluation_cycle()
    if result:
        print(f"  结论: {result.conclusion.value}")
        print(f"  建议操作: {result.suggested_action}")

    print_separator("STEP 4: 连续重试升级")
    evaluator._retry_counters["S04"] = 3  # 模拟已重试3次
    evaluator.set_execution_result_query(lambda: ToolExecutionResult(
        step_id="S04", plan_id="P04", tool_name="api",
        status="failure", error_code="TIMEOUT"
    ))
    result = evaluator.run_evaluation_cycle()
    if result:
        print(f"  结论: {result.conclusion.value}")
        print(f"  建议操作: {result.suggested_action}")

    print("\n✅ 结果评估模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-06 结果评估模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_evaluator():
            return ResultEvaluator()

        # TC-E06-01: 成功结果评估
        print("\n[TC-E06-01] 成功结果评估")
        try:
            e = setup_evaluator()
            e.set_execution_result_query(lambda: ToolExecutionResult(
                step_id="T01", plan_id="P01", tool_name="test",
                status="success", output_data={"key": "value"}
            ))
            result = e.run_evaluation_cycle()
            assert result is not None
            assert result.conclusion in (EvaluationConclusion.SUCCESS, EvaluationConclusion.SUCCESS_WITH_DEVIATION)
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E06-02: 临时性错误建议重试
        print("\n[TC-E06-02] 临时性错误建议重试")
        try:
            ev = setup_evaluator()
            ev.set_execution_result_query(lambda: ToolExecutionResult(
                step_id="T02", plan_id="P02", status="failure", error_code="TIMEOUT"
            ))
            result = ev.run_evaluation_cycle()
            assert result is not None
            assert result.conclusion == EvaluationConclusion.RETRY_NEEDED
            assert result.suggested_action == "自动重试"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E06-03: 权限不足直接失败
        print("\n[TC-E06-03] 权限不足直接失败")
        try:
            ev = setup_evaluator()
            ev.set_execution_result_query(lambda: ToolExecutionResult(
                step_id="T03", plan_id="P03", status="failure", error_code="PERMISSION_DENIED"
            ))
            result = ev.run_evaluation_cycle()
            assert result is not None
            assert result.conclusion == EvaluationConclusion.FAILURE_UNRECOVERABLE
            assert result.suggested_action == "需用户授权"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E06-04: 连续3次重试升级
        print("\n[TC-E06-04] 连续3次重试升级")
        try:
            ev = setup_evaluator()
            ev._retry_counters["T04"] = 3
            ev.set_execution_result_query(lambda: ToolExecutionResult(
                step_id="T04", plan_id="P04", status="failure", error_code="TIMEOUT"
            ))
            result = ev.run_evaluation_cycle()
            assert result is not None
            assert result.conclusion == EvaluationConclusion.FAILURE_UNRECOVERABLE
            assert "连续重试" in result.suggested_action
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E06-05: 工具不可用建议切换备选
        print("\n[TC-E06-05] 工具不可用建议切换备选")
        try:
            ev = setup_evaluator()
            ev.set_execution_result_query(lambda: ToolExecutionResult(
                step_id="T05", plan_id="P05", status="failure", error_code="SERVICE_UNAVAILABLE"
            ))
            result = ev.run_evaluation_cycle()
            assert result is not None
            assert result.suggested_action == "切换备选工具"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E06-06: 紧急熔断
        print("\n[TC-E06-06] 紧急熔断")
        try:
            ev = setup_evaluator()
            ev.emergency_shutdown()
            assert ev.state == EvaluatorState.SYSTEM_PAUSED
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