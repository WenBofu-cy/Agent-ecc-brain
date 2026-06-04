#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-02
模块名称: 任务规划模块
所属分区: 一、认知大脑核心模块
核心职责: 接收 ag-ecc-01（意图解析模块）输出的结构化意图描述，将用户的高层任务目标拆解
          为可执行的有序步骤序列。评估每一步骤的前置依赖、资源需求与预期耗时，生成完整的
          任务执行计划。同时负责管理任务的全生命周期——包括任务队列的优先级排序、执行进度
          跟踪、异常中断后的恢复规划。支持多任务并发的调度编排。不参与具体工具的选择或执行，
          仅负责任务的逻辑拆解与流程编排。

依赖模块:
    ag-ecc-01(意图解析模块), ag-ecc-03(工具选择模块), ag-ecc-05(记忆查询模块),
    ag-ecc-07(工作记忆模块), ag-ecc-04(安全仲裁模块), ag-ecc-06(结果评估模块),
    ag-ecc-09(内生动机模块)
被依赖模块:
    ag-ecc-03, ag-ecc-04, ag-ecc-06, ag-ecc-09, ag-ecc-07

安全约束:
  T-01: 所有任务执行计划在下发前必须通过 ag-ecc-04 安全仲裁模块的审查，未通过的计划不得执行
  T-02: 涉及系统配置修改或敏感数据访问的步骤，必须在计划中明确标注"需用户确认"
  T-03: 任务队列中的用户显式任务优先级永远高于系统自主生成的任务
  T-04: 任务执行计划中的预估耗时不得作为硬性超时截止时间，仅用于进度展示
  T-05: 本模块仅负责步骤的逻辑拆解，不得直接调用任何工具或访问外部资源
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class PlannerState(Enum):
    WAITING_INTENT = "waiting_intent"
    PLANNING = "planning"
    AWAITING_RESOURCES = "awaiting_resources"
    EXECUTING = "executing"
    ERROR_RECOVERY = "error_recovery"
    SYSTEM_PAUSED = "system_paused"


class TaskType(Enum):
    INFO_QUERY = "信息查询"
    TOOL_CALL = "工具调用"
    CONTENT_CREATION = "内容创作"
    DIALOGUE = "对话交互"
    TASK_MANAGE = "任务管理"
    SYSTEM_CONFIG = "系统配置"
    GENERAL = "通用任务"


@dataclass
class StructuredIntent:
    intent_id: str = ""
    session_id: str = ""
    task_type: TaskType = TaskType.DIALOGUE
    entities: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskStep:
    step_id: str = ""
    description: str = ""
    required_tool_type: str = ""
    depends_on: List[str] = field(default_factory=list)
    estimated_duration_sec: float = 30.0
    retry_policy: str = "no_retry"
    max_retries: int = 0
    needs_user_confirmation: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    plan_id: str = ""
    intent_id: str = ""
    task_type: TaskType = TaskType.GENERAL
    steps: List[TaskStep] = field(default_factory=list)
    estimated_total_duration_sec: float = 0.0
    priority: int = 5
    is_autonomous: bool = False
    status: str = "planned"
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class SafetyReviewRequest:
    plan_id: str = ""
    task_type: TaskType = TaskType.GENERAL
    steps: List[TaskStep] = field(default_factory=list)


@dataclass
class SafetyReviewResult:
    plan_id: str = ""
    approved: bool = True
    rejected_reason: str = ""


@dataclass
class StepResourceRequirement:
    step_id: str = ""
    plan_id: str = ""
    required_tool_type: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    deadline_sec: float = 0.0


@dataclass
class StepExecutionReceipt:
    step_id: str = ""
    plan_id: str = ""
    status: str = "success"
    output_summary: Dict[str, Any] = field(default_factory=dict)
    duration_sec: float = 0.0
    error_code: str = ""


@dataclass
class RecoveryPlan:
    original_plan_id: str = ""
    failed_step_id: str = ""
    alternative_steps: List[TaskStep] = field(default_factory=list)
    rollback_steps: List[TaskStep] = field(default_factory=list)


@dataclass
class PlannerStatus:
    state: PlannerState = PlannerState.WAITING_INTENT
    active_tasks: int = 0
    queue_depth: int = 0
    avg_planning_duration_ms: float = 0.0


class TaskPlanner:
    DECOMPOSE_STRATEGIES = {
        TaskType.INFO_QUERY: [
            TaskStep(description="确定查询源", required_tool_type="SEARCH"),
            TaskStep(description="执行查询", required_tool_type="API"),
            TaskStep(description="整理查询结果", required_tool_type="FORMAT"),
        ],
        TaskType.TOOL_CALL: [
            TaskStep(description="准备调用参数", required_tool_type="PARAM"),
            TaskStep(description="执行工具调用", required_tool_type="API"),
            TaskStep(description="校验返回结果", required_tool_type="VALIDATE"),
        ],
        TaskType.CONTENT_CREATION: [
            TaskStep(description="澄清创作需求", required_tool_type="DIALOGUE"),
            TaskStep(description="规划内容大纲", required_tool_type="REASON"),
            TaskStep(description="生成内容", required_tool_type="GENERATE"),
            TaskStep(description="润色与排版", required_tool_type="FORMAT"),
        ],
        TaskType.DIALOGUE: [
            TaskStep(description="生成回复", required_tool_type="DIALOGUE"),
        ],
        TaskType.TASK_MANAGE: [
            TaskStep(description="查找目标任务", required_tool_type="SEARCH"),
            TaskStep(description="执行管理操作", required_tool_type="API"),
            TaskStep(description="确认结果", required_tool_type="VALIDATE"),
        ],
        TaskType.SYSTEM_CONFIG: [
            TaskStep(description="校验当前配置", required_tool_type="READ"),
            TaskStep(description="写入新配置", required_tool_type="WRITE"),
            TaskStep(description="验证生效", required_tool_type="VERIFY"),
        ],
        TaskType.GENERAL: [
            TaskStep(description="执行通用任务", required_tool_type="GENERAL"),
        ],
    }

    MAX_QUEUE_SIZE = 20
    STATUS_REPORT_INTERVAL_SEC = 30

    def __init__(self):
        self.module_id = "ag-ecc-02"
        self.module_name = "任务规划模块"
        self.version = "V1.0"

        self.state = PlannerState.WAITING_INTENT
        self._task_queue: List[StructuredIntent] = []
        self._active_tasks: Dict[str, TaskPlan] = {}
        self._total_planned: int = 0
        self._total_planning_time: float = 0.0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_intent = None
        self._query_tool_constraints = None
        self._query_historical_templates = None
        self._query_step_execution_receipt = None
        self._query_autonomous_task = None
        self._query_safety_review_result = None

        self._publish_plan = None
        self._publish_step_requirements = None
        self._publish_task_status = None
        self._publish_recovery_plan = None
        self._publish_status_report = None
        self._publish_safety_review = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_intent_query(self, callback: Callable[[], Optional[StructuredIntent]]):
        self._query_intent = callback

    def set_tool_constraints_query(self, callback: Callable[[], Optional[Dict[str, Any]]]):
        self._query_tool_constraints = callback

    def set_historical_templates_query(self, callback: Callable[[TaskType, Dict[str, Any]], Optional[List[TaskStep]]]):
        self._query_historical_templates = callback

    def set_step_execution_receipt_query(self, callback: Callable[[], Optional[StepExecutionReceipt]]):
        self._query_step_execution_receipt = callback

    def set_autonomous_task_query(self, callback: Callable[[], Optional[TaskPlan]]):
        self._query_autonomous_task = callback

    def set_safety_review_result_query(self, callback: Callable[[str], Optional[SafetyReviewResult]]):
        self._query_safety_review_result = callback

    def set_plan_publisher(self, callback: Callable[[TaskPlan], None]):
        self._publish_plan = callback

    def set_step_requirements_publisher(self, callback: Callable[[StepResourceRequirement], None]):
        self._publish_step_requirements = callback

    def set_task_status_publisher(self, callback: Callable[[str, str, Dict[str, Any]], None]):
        self._publish_task_status = callback

    def set_recovery_plan_publisher(self, callback: Callable[[RecoveryPlan], None]):
        self._publish_recovery_plan = callback

    def set_status_report_publisher(self, callback: Callable[[PlannerStatus], None]):
        self._publish_status_report = callback

    def set_safety_review_publisher(self, callback: Callable[[SafetyReviewRequest], None]):
        self._publish_safety_review = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_planning_cycle(self) -> Optional[TaskPlan]:
        now = time.time()

        if self.state == PlannerState.SYSTEM_PAUSED:
            return None

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理步骤执行回执
        if self.state == PlannerState.EXECUTING:
            receipt = self._query_step_execution_receipt() if self._query_step_execution_receipt else None
            if receipt:
                self._handle_execution_receipt(receipt)

        # 处理自主目标任务（优先级低于用户任务）
        auto_task = self._query_autonomous_task() if self._query_autonomous_task else None
        if auto_task and self.state == PlannerState.WAITING_INTENT:
            # 将自主任务包装为意图并入队
            auto_intent = StructuredIntent(
                intent_id=auto_task.plan_id,
                task_type=auto_task.task_type,
                priority=8,
                confidence=0.5
            )
            self._enqueue_intent(auto_intent)

        # 处理新意图
        intent = self._query_intent() if self._query_intent else None
        if intent is None:
            return None

        if self.state != PlannerState.WAITING_INTENT:
            # 加入队列等待
            if len(self._task_queue) < self.MAX_QUEUE_SIZE:
                self._task_queue.append(intent)
            return None

        return self._handle_new_intent(intent)

    # ========== 新意图处理 ==========
    def _handle_new_intent(self, intent: StructuredIntent) -> Optional[TaskPlan]:
        self.state = PlannerState.PLANNING
        start_time = time.time()
        plan_id = f"PLAN-{uuid.uuid4().hex[:8]}"

        strategy = self.DECOMPOSE_STRATEGIES.get(
            intent.task_type,
            self.DECOMPOSE_STRATEGIES[TaskType.GENERAL]
        )

        # 查询历史模板
        if self._query_historical_templates:
            historical_steps = self._query_historical_templates(intent.task_type, intent.entities)
            if historical_steps:
                strategy = historical_steps

        steps = self._generate_steps(intent, strategy)

        plan = TaskPlan(
            plan_id=plan_id,
            intent_id=intent.intent_id,
            task_type=intent.task_type,
            steps=steps,
            estimated_total_duration_sec=sum(s.estimated_duration_sec for s in steps),
            priority=intent.priority,
            is_autonomous=False,
            status="planned"
        )

        # 安全审查（修复 T-01）
        if self._publish_safety_review:
            self._publish_safety_review(SafetyReviewRequest(
                plan_id=plan_id,
                task_type=intent.task_type,
                steps=steps
            ))
            # 等待审查结果
            review_result = self._query_safety_review_result(plan_id) if self._query_safety_review_result else None
            if review_result and not review_result.approved:
                plan.status = "rejected"
                self.state = PlannerState.WAITING_INTENT
                self._log_event("PLAN_REJECTED", {"plan_id": plan_id, "reason": review_result.rejected_reason})
                return None

        # 资源确认
        self.state = PlannerState.AWAITING_RESOURCES
        if self._publish_step_requirements and steps:
            for step in steps:
                self._publish_step_requirements(StepResourceRequirement(
                    step_id=step.step_id, plan_id=plan_id,
                    required_tool_type=step.required_tool_type,
                    parameters=step.parameters
                ))

        # 下发计划
        self._active_tasks[plan_id] = plan
        self._total_planned += 1
        elapsed = (time.time() - start_time) * 1000
        self._total_planning_time += elapsed

        if self._publish_plan:
            self._publish_plan(plan)

        self.state = PlannerState.EXECUTING
        return plan

    def _generate_steps(self, intent: StructuredIntent, strategy: List[TaskStep]) -> List[TaskStep]:
        steps = []
        for i, template in enumerate(strategy):
            step = TaskStep(
                step_id=f"STEP-{i+1}-{uuid.uuid4().hex[:8]}",
                description=template.description,
                required_tool_type=template.required_tool_type,
                depends_on=[s.step_id for s in steps] if i > 0 else [],
                retry_policy=template.retry_policy,
                max_retries=template.max_retries,
                needs_user_confirmation=template.needs_user_confirmation,
                parameters=intent.entities if i == 1 else {}
            )
            steps.append(step)
        return steps

    # ========== 执行回执处理 ==========
    def _handle_execution_receipt(self, receipt: StepExecutionReceipt):
        plan = self._active_tasks.get(receipt.plan_id)
        if not plan:
            return

        if receipt.status == "success":
            plan.current_step_index += 1
            plan.updated_at = time.time()

            if plan.current_step_index >= len(plan.steps):
                plan.status = "completed"
                if self._publish_task_status:
                    self._publish_task_status(plan.plan_id, "completed", {"total_duration": plan.estimated_total_duration_sec})
                self._active_tasks.pop(receipt.plan_id, None)
                self._process_next_task()
            else:
                plan.status = "executing"
                if self._publish_task_status:
                    self._publish_task_status(plan.plan_id, "in_progress", {"current_step": plan.current_step_index + 1, "total_steps": len(plan.steps)})
        else:
            self.state = PlannerState.ERROR_RECOVERY
            recovery = self._generate_recovery(plan, receipt)
            if self._publish_recovery_plan:
                self._publish_recovery_plan(recovery)

    def _generate_recovery(self, plan: TaskPlan, receipt: StepExecutionReceipt) -> RecoveryPlan:
        failed_step = plan.steps[plan.current_step_index] if plan.current_step_index < len(plan.steps) else None
        alt_steps = []
        if failed_step and receipt.error_code in ("TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"):
            alt_steps = [TaskStep(description=f"重试: {failed_step.description}", required_tool_type=failed_step.required_tool_type)]
        elif failed_step and receipt.error_code in ("INVALID_PARAM", "MISSING_PARAM"):
            alt_steps = [TaskStep(description=f"补充参数后重试: {failed_step.description}", required_tool_type=failed_step.required_tool_type)]

        return RecoveryPlan(
            original_plan_id=plan.plan_id,
            failed_step_id=receipt.step_id,
            alternative_steps=alt_steps,
            rollback_steps=[]
        )

    def _process_next_task(self):
        if self._task_queue:
            next_intent = self._task_queue.pop(0)
            self._handle_new_intent(next_intent)
        else:
            self.state = PlannerState.WAITING_INTENT

    def _enqueue_intent(self, intent: StructuredIntent):
        if len(self._task_queue) < self.MAX_QUEUE_SIZE:
            self._task_queue.append(intent)
            self._task_queue.sort(key=lambda i: i.priority)

    # ========== 辅助 ==========
    def _publish_status(self):
        if self._publish_status_report:
            avg = self._total_planning_time / max(self._total_planned, 1)
            self._publish_status_report(PlannerStatus(
                state=self.state,
                active_tasks=len(self._active_tasks),
                queue_depth=len(self._task_queue),
                avg_planning_duration_ms=round(avg, 2)
            ))

    def get_state(self) -> PlannerState:
        return self.state

    def emergency_shutdown(self):
        self.state = PlannerState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 任务规划模块 (ag-ecc-02) 演示")
    print("=" * 70)

    planner = TaskPlanner()
    # 注入安全审查回调（默认通过）
    planner.set_safety_review_publisher(lambda req: None)
    planner.set_safety_review_result_query(lambda pid: SafetyReviewResult(plan_id=pid, approved=True))

    print_separator("STEP 1: 接收工具调用意图并生成计划")
    planner.set_intent_query(lambda: StructuredIntent(
        intent_id="INT-001", session_id="S001",
        task_type=TaskType.TOOL_CALL,
        entities={"tool": "weather_api", "city": "北京"},
        priority=3, confidence=0.9
    ))
    plan = planner.run_planning_cycle()
    if plan:
        print(f"  计划ID: {plan.plan_id}")
        print(f"  任务类型: {plan.task_type.value}")
        print(f"  步骤数: {len(plan.steps)}")
        for s in plan.steps:
            print(f"    - {s.step_id}: {s.description}")

    print_separator("STEP 2: 安全审查拒绝演示")
    planner.set_safety_review_result_query(lambda pid: SafetyReviewResult(plan_id=pid, approved=False, rejected_reason="测试拒绝"))
    planner.set_intent_query(lambda: StructuredIntent(
        intent_id="INT-002", task_type=TaskType.TOOL_CALL, priority=3
    ))
    plan2 = planner.run_planning_cycle()
    if plan2 is None:
        print("  计划被安全仲裁拒绝，未下发")

    print("\n✅ 任务规划模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-02 任务规划模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_planner():
            p = TaskPlanner()
            p.set_safety_review_publisher(lambda req: None)
            p.set_safety_review_result_query(lambda pid: SafetyReviewResult(plan_id=pid, approved=True))
            return p

        # TC-E02-01: 工具调用意图生成3步计划
        print("\n[TC-E02-01] 工具调用意图生成3步计划")
        try:
            p = setup_planner()
            p.set_intent_query(lambda: StructuredIntent(
                intent_id="T01", task_type=TaskType.TOOL_CALL,
                entities={"tool": "test"}, priority=3
            ))
            plan = p.run_planning_cycle()
            assert plan is not None
            assert len(plan.steps) == 3
            assert plan.steps[0].description == "准备调用参数"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E02-02: 对话交互意图生成单步计划
        print("\n[TC-E02-02] 对话交互意图生成单步计划")
        try:
            p = setup_planner()
            p.set_intent_query(lambda: StructuredIntent(
                intent_id="T02", task_type=TaskType.DIALOGUE, priority=5
            ))
            plan = p.run_planning_cycle()
            assert plan is not None
            assert len(plan.steps) == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E02-03: 步骤执行成功推进进度
        print("\n[TC-E02-03] 步骤执行成功推进进度")
        try:
            p = setup_planner()
            p.set_intent_query(lambda: StructuredIntent(
                intent_id="T03", task_type=TaskType.TOOL_CALL, entities={"tool": "test"}, priority=3
            ))
            plan = p.run_planning_cycle()
            first_step_id = plan.steps[0].step_id
            p.set_step_execution_receipt_query(lambda: StepExecutionReceipt(
                step_id=first_step_id, plan_id=plan.plan_id, status="success"
            ))
            p.run_planning_cycle()
            assert plan.current_step_index == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E02-04: 异常回执触发恢复计划
        print("\n[TC-E02-04] 异常回执触发恢复计划")
        try:
            p = setup_planner()
            p.set_intent_query(lambda: StructuredIntent(
                intent_id="T04", task_type=TaskType.TOOL_CALL, entities={"tool": "test"}, priority=3
            ))
            plan = p.run_planning_cycle()
            p.set_step_execution_receipt_query(lambda: StepExecutionReceipt(
                step_id=plan.steps[0].step_id, plan_id=plan.plan_id, status="failure", error_code="TIMEOUT"
            ))
            p.run_planning_cycle()
            assert p.state == PlannerState.ERROR_RECOVERY
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E02-05: 安全审查拒绝不下发计划
        print("\n[TC-E02-05] 安全审查拒绝不下发计划")
        try:
            p = TaskPlanner()
            p.set_safety_review_publisher(lambda req: None)
            p.set_safety_review_result_query(lambda pid: SafetyReviewResult(plan_id=pid, approved=False, rejected_reason="测试"))
            p.set_intent_query(lambda: StructuredIntent(
                intent_id="T05", task_type=TaskType.TOOL_CALL, priority=3
            ))
            plan = p.run_planning_cycle()
            assert plan is None
            assert p.state == PlannerState.WAITING_INTENT
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E02-06: 紧急熔断
        print("\n[TC-E02-06] 紧急熔断")
        try:
            p = setup_planner()
            p.emergency_shutdown()
            assert p.state == PlannerState.SYSTEM_PAUSED
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