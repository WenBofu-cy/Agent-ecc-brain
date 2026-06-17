#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-02
模块名称: 任务规划模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责:
  接收 ag-ecc-01 输出的结构化意图描述，将高层任务目标拆解为可执行的有序步骤序列。
  评估每一步骤的前置依赖、资源需求与预期耗时，生成完整的任务执行计划。
  管理任务的全生命周期——包括任务队列的优先级排序、执行进度跟踪、异常中断后的恢复规划。
  支持多任务并发的调度编排。不参与具体工具的选择或执行，仅负责任务的逻辑拆解与流程编排。

依赖模块:
  ag-ecc-01, ag-ecc-03, ag-ecc-05, ag-ecc-07, ag-ecc-04, ag-ecc-06, ag-ecc-09
被依赖模块:
  ag-ecc-03, ag-ecc-04, ag-ecc-06, ag-ecc-09, ag-ecc-07

安全约束:
  T-01: 所有任务执行计划在下发前必须通过 ag-ecc-04 安全仲裁模块的审查，未通过的计划不得执行
  T-02: 涉及系统配置修改或敏感数据访问的步骤，必须在计划中明确标注"需用户确认"
  T-03: 任务队列中的用户显式任务优先级永远高于系统自主生成的任务
  T-04: 任务执行计划中的预估耗时不得作为硬性超时截止时间，仅用于进度展示
  T-05: 本模块仅负责步骤的逻辑拆解，不得直接调用任何工具或访问外部资源
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

# 总线消息结构
from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_CRITICAL


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ag-ecc-02")


# ==================== 状态与类型定义 ====================
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredIntent":
        """从字典反序列化，处理枚举转换"""
        task_type_str = data.get("task_type", "对话交互")
        if isinstance(task_type_str, TaskType):
            return cls(**data)
        for t in TaskType:
            if t.value == task_type_str:
                data["task_type"] = t
                break
        else:
            data["task_type"] = TaskType.DIALOGUE
        return cls(**data)


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

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


@dataclass
class TaskPlan:
    plan_id: str = ""
    intent_id: str = ""
    session_id: str = ""  # 新增：关联会话ID
    task_type: TaskType = TaskType.GENERAL
    steps: List[TaskStep] = field(default_factory=list)
    estimated_total_duration_sec: float = 0.0
    priority: int = 5
    is_autonomous: bool = False
    status: str = "planned"
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "session_id": self.session_id,  # 新增：序列化会话ID
            "task_type": self.task_type.value,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_total_duration_sec": self.estimated_total_duration_sec,
            "priority": self.priority,
            "is_autonomous": self.is_autonomous,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class TaskPlanner:
    """任务规划模块 V1.0"""

    DECOMPOSE_STRATEGIES = {
        TaskType.INFO_QUERY: [
            ("确定查询源", "SEARCH"),
            ("执行查询", "API"),
            ("整理查询结果", "FORMAT"),
        ],
        TaskType.TOOL_CALL: [
            ("准备调用参数", "PARAM"),
            ("执行工具调用", "API"),
            ("校验返回结果", "VALIDATE"),
        ],
        TaskType.CONTENT_CREATION: [
            ("澄清创作需求", "DIALOGUE"),
            ("规划内容大纲", "REASON"),
            ("生成内容", "GENERATE"),
            ("润色与排版", "FORMAT"),
        ],
        TaskType.DIALOGUE: [
            ("生成回复", "DIALOGUE"),
        ],
        TaskType.TASK_MANAGE: [
            ("查找目标任务", "SEARCH"),
            ("执行管理操作", "API"),
            ("确认结果", "VALIDATE"),
        ],
        TaskType.SYSTEM_CONFIG: [
            ("校验当前配置", "READ"),
            ("写入新配置", "WRITE"),
            ("验证生效", "VERIFY"),
        ],
        TaskType.GENERAL: [
            ("分析任务目标", "REASON"),
            ("选择执行路径", "DECISION"),
            ("执行通用操作", "GENERAL"),
        ],
    }

    MAX_QUEUE_SIZE = 20

    def __init__(self):
        self.module_id = "ag-ecc-02"
        self.version = "V1.0"
        self.state = PlannerState.WAITING_INTENT
        self.bus = None

        # 统计相关变量
        self._last_status_time = time.time()
        self._total_planned = 0
        self._total_planning_time = 0.0

        self._task_queue: List[StructuredIntent] = []
        self._active_plans: Dict[str, TaskPlan] = {}
        self._intent_buffer: List[StructuredIntent] = []
        self._receipt_buffer: List[Dict] = []
        self._review_buffer: List[Dict] = []
        self._interrupt_buffer: List[Dict] = []
        logger.info("任务规划模块初始化完成")

    def handle_message(self, msg: Message):
        """接收总线消息（点对点订阅模式）"""
        try:
            topic = msg.topic
            if topic == "ag-ecc-02.intent_parsed":
                intent_data = msg.data
                intent = StructuredIntent.from_dict(intent_data)
                logger.info(f"收到新意图，intent_id: {intent.intent_id}, 类型: {intent.task_type.value}")
                self._intent_buffer.append(intent)

            elif topic == "ag-ecc-02.step_completed":
                logger.info(f"收到步骤执行回执，plan_id: {msg.data.get('plan_id')}")
                self._receipt_buffer.append(msg.data)

            elif topic == "ag-ecc-02.review_result":
                logger.info(f"收到安全审查结果，plan_id: {msg.data.get('plan_id')}")
                self._review_buffer.append(msg.data)  # 追加到列表末尾

            elif topic == "ag-ecc-02.task_interrupted":
                logger.warning(f"收到任务中断通知，plan_id: {msg.data.get('plan_id')}")
                self._interrupt_buffer.append(msg.data)

            elif topic == "ag-ecc-02.autonomous_task":
                auto_data = msg.data
                task_type = TaskType.GENERAL
                type_str = auto_data.get("task_type", "GENERAL")
                try:
                    task_type = TaskType[type_str]
                except KeyError:
                    for t in TaskType:
                        if t.value == type_str:
                            task_type = t
                            break
                auto_intent = StructuredIntent(
                    intent_id=auto_data.get("plan_id", f"AUTO-{uuid.uuid4().hex[:8]}"),
                    session_id=auto_data.get("session_id", "AUTO"),
                    task_type=task_type,
                    priority=8,
                    confidence=0.5
                )
                logger.info(f"收到自主任务，intent_id: {auto_intent.intent_id}")
                self._intent_buffer.append(auto_intent)

            elif topic == "ag-ecc-02.shutdown":
                logger.info("收到关闭指令")
                self.emergency_shutdown()

            elif topic == "ag-ecc-02.resume":
                logger.info("收到恢复指令")
                if self.state == PlannerState.SYSTEM_PAUSED:
                    self.state = PlannerState.WAITING_INTENT

            else:
                logger.debug(f"忽略不相关消息: {topic}")

        except Exception as e:
            logger.error(f"处理消息异常: {str(e)}", exc_info=True)

    # ====================== 主循环 ======================
    def task_planner_main_loop(self):
        """主循环，CPEC 规定的方法名"""
        if self.state == PlannerState.SYSTEM_PAUSED:
            return

        try:
            now = time.time()
            if now - self._last_status_time >= 30:
                self._publish_status()
                self._last_status_time = now

            # 处理中断通知
            while self._interrupt_buffer:
                data = self._interrupt_buffer.pop(0)
                self._handle_interrupt(data)

            # 处理执行回执
            while self._receipt_buffer:
                receipt = self._receipt_buffer.pop(0)
                self._handle_execution_receipt(receipt)

            # 处理安全审查结果（FIFO）
            while self._review_buffer:
                review = self._review_buffer.pop(0)
                plan_id = review["plan_id"]
                self._handle_review_result(plan_id, review)

            # 处理新意图
            if self._intent_buffer:
                for intent in self._intent_buffer:
                    self._enqueue_intent(intent)
                self._intent_buffer.clear()

            # 空闲时从队列取任务规划
            if self.state == PlannerState.WAITING_INTENT and self._task_queue:
                next_intent = self._task_queue.pop(0)
                self._start_planning(next_intent)

        except Exception as e:
            logger.error(f"主循环异常: {str(e)}", exc_info=True)

    def _handle_interrupt(self, data: Dict):
        """处理任务中断通知（来自 ag-ecc-06）"""
        plan_id = data.get("plan_id")
        interrupted_step = data.get("step_id")
        reason = data.get("interrupt_reason", "未知原因")
        logger.warning(f"任务中断，plan_id: {plan_id}, step: {interrupted_step}, 原因: {reason}")

        plan = self._active_plans.pop(plan_id, None)
        if plan:
            plan.status = "interrupted"
            # 发送中断状态更新
            self._publish_task_status(plan_id, "interrupted")
            # 生成恢复计划并发送给结果评估模块
            recovery = {
                "original_plan_id": plan_id,
                "failed_step_id": interrupted_step,
                "alternative_steps": [],
                "rollback_steps": [],
                "reason": reason
            }
            self._publish_recovery_plan(recovery)

    def _start_planning(self, intent: StructuredIntent):
        """开始为一个意图生成执行计划"""
        self.state = PlannerState.PLANNING
        start_time = time.time()

        try:
            plan_id = f"PLAN-{uuid.uuid4().hex[:8]}"
            strategy = self._get_decompose_strategy(intent.task_type)
            logger.info(f"开始规划，intent_id: {intent.intent_id}, plan_id: {plan_id}")

            template_steps = self._query_historical_template(intent.task_type, intent.entities)
            if template_steps:
                logger.info(f"使用历史模板，intent_id: {intent.intent_id}")
                strategy = template_steps

            steps = self._generate_steps(intent, strategy)

            plan = TaskPlan(
                plan_id=plan_id,
                intent_id=intent.intent_id,
                session_id=intent.session_id,  # 新增：保存会话ID
                task_type=intent.task_type,
                steps=steps,
                estimated_total_duration_sec=sum(s.estimated_duration_sec for s in steps),
                priority=intent.priority,
                is_autonomous=(intent.confidence < 0.6),
                status="planned"
            )

            self.state = PlannerState.AWAITING_RESOURCES
            constraints = self._query_tool_constraints(steps)
            self._adjust_steps_by_constraints(steps, constraints)

            self._send_safety_review(plan)
            self._active_plans[plan_id] = plan
            self._total_planned += 1
            elapsed = (time.time() - start_time) * 1000
            self._total_planning_time += elapsed
            logger.info(f"规划完成，plan_id: {plan_id}, 耗时: {elapsed:.2f}ms, 步骤数: {len(steps)}")

        except Exception as e:
            logger.error(f"规划失败，intent_id: {intent.intent_id}, 错误: {str(e)}", exc_info=True)
            self._send_plan_failed(intent.session_id, intent.intent_id, "PLANNING_ERROR", f"规划异常: {str(e)}")

        self.state = PlannerState.WAITING_INTENT

    def _handle_review_result(self, plan_id: str, review: Dict):
        try:
            plan = self._active_plans.get(plan_id)
            if not plan:
                logger.warning(f"收到未知计划的审查结果，plan_id: {plan_id}")
                return

            if not review.get("approved", False):
                plan.status = "rejected"
                del self._active_plans[plan_id]
                reason = review.get("rejected_reason", "未知原因")
                logger.warning(f"计划被拒绝，plan_id: {plan_id}, 原因: {reason}")
                # 修正：传入正确的session_id和intent_id
                self._send_plan_failed(plan.session_id, plan.intent_id, "REJECTED", f"安全审查不通过: {reason}")
                return

            logger.info(f"计划审查通过，plan_id: {plan_id}")
            self._publish_plan_and_requirements(plan)
            plan.status = "executing"
            self.state = PlannerState.EXECUTING

        except Exception as e:
            logger.error(f"处理审查结果异常，plan_id: {plan_id}, 错误: {str(e)}", exc_info=True)

    def _handle_execution_receipt(self, receipt: Dict):
        try:
            plan_id = receipt.get("plan_id")
            plan = self._active_plans.get(plan_id)
            if not plan:
                logger.warning(f"收到未知计划的执行回执，plan_id: {plan_id}")
                return

            status = receipt.get("status", "success")
            logger.info(f"步骤执行回执，plan_id: {plan_id}, 状态: {status}")

            if status == "success":
                plan.current_step_index += 1
                plan.updated_at = time.time()
                if plan.current_step_index >= len(plan.steps):
                    plan.status = "completed"
                    logger.info(f"任务完成，plan_id: {plan_id}")
                    self._publish_task_status(plan.plan_id, "completed")
                    del self._active_plans[plan_id]
                else:
                    self._publish_task_status(plan.plan_id, "in_progress")
                self.state = PlannerState.WAITING_INTENT

            else:
                self.state = PlannerState.ERROR_RECOVERY
                logger.warning(f"步骤执行失败，plan_id: {plan_id}, 错误: {receipt.get('error_msg')}")
                recovery = self._generate_recovery(plan, receipt)
                self._publish_recovery_plan(recovery)
                self.state = PlannerState.WAITING_INTENT

        except Exception as e:
            logger.error(f"处理执行回执异常，plan_id: {plan_id}, 错误: {str(e)}", exc_info=True)

    # ====================== 步骤生成 ======================
    def _get_decompose_strategy(self, task_type: TaskType) -> List[Tuple[str, str]]:
        return self.DECOMPOSE_STRATEGIES.get(task_type, self.DECOMPOSE_STRATEGIES[TaskType.GENERAL])

    def _generate_steps(self, intent: StructuredIntent, strategy: List[Tuple[str, str]]) -> List[TaskStep]:
        steps = []
        for i, (desc, tool_type) in enumerate(strategy):
            step = TaskStep(
                step_id=f"STEP-{i+1}-{uuid.uuid4().hex[:8]}",
                description=desc,
                required_tool_type=tool_type,
                depends_on=[steps[-1].step_id] if steps else [],
                parameters=intent.entities,
                needs_user_confirmation=(intent.task_type == TaskType.SYSTEM_CONFIG and i == 1)
            )
            steps.append(step)
        return steps

    # ====================== 总线通信 ======================
    def _query_historical_template(self, task_type: TaskType, entities: Dict) -> Optional[List[Tuple[str, str]]]:
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic="ag-ecc-05.query_template",
                source_module=self.module_id,
                data={"task_type": task_type.value, "entities": entities},
                target_module="ag-ecc-05",
                timeout_ms=1000
            )
            if resp and resp.data:
                return [(s["description"], s["tool_type"]) for s in resp.data.get("steps", [])]
            return None
        except Exception as e:
            logger.error(f"查询历史模板异常: {str(e)}")
            return None

    def _query_tool_constraints(self, steps: List[TaskStep]) -> Dict[str, Any]:
        if not self.bus:
            return {}
        try:
            resp = self.bus.request(
                topic="ag-ecc-03.query_constraints",
                source_module=self.module_id,
                data={"required_tools": [s.required_tool_type for s in steps]},
                target_module="ag-ecc-03",
                timeout_ms=1000
            )
            return resp.data if resp else {}
        except Exception as e:
            logger.error(f"查询工具约束异常: {str(e)}")
            return {}

    def _adjust_steps_by_constraints(self, steps: List[TaskStep], constraints: Dict):
        unavailable = constraints.get("unavailable_tools", [])
        for step in steps:
            if step.required_tool_type in unavailable:
                step.needs_user_confirmation = True

    def _send_safety_review(self, plan: TaskPlan):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="review_request",
                source_module=self.module_id,
                data={
                    "plan_id": plan.plan_id,
                    "task_type": plan.task_type.value,
                    "steps": [s.to_dict() for s in plan.steps],
                },
                priority=PRIORITY_HIGH
            )

    def _publish_plan_and_requirements(self, plan: TaskPlan):
        if not self.bus:
            return
        self.bus.publish_to_module(
            target_module="ag-ecc-03",
            event_type="task_plan",
            source_module=self.module_id,
            data=plan.to_dict(),
            priority=PRIORITY_HIGH
        )
        for step in plan.steps:
            self.bus.publish_to_module(
                target_module="ag-ecc-03",
                event_type="step_requirement",
                source_module=self.module_id,
                data={
                    "step_id": step.step_id,
                    "plan_id": plan.plan_id,
                    "required_tool_type": step.required_tool_type,
                    "parameters": step.parameters,
                },
                priority=PRIORITY_NORMAL
            )

    def _publish_task_status(self, plan_id: str, status: str):
        if self.bus:
            plan = self._active_plans.get(plan_id)
            self.bus.publish_to_module(
                target_module="ag-ecc-07",
                event_type="task_status",
                source_module=self.module_id,
                data={
                    "plan_id": plan_id,
                    "status": status,
                    "current_step": plan.current_step_index + 1 if plan else 0,
                    "total_steps": len(plan.steps) if plan else 0
                },
                priority=PRIORITY_NORMAL
            )

    def _publish_recovery_plan(self, recovery: Dict):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-06",
                event_type="recovery_plan",
                source_module=self.module_id,
                data=recovery,
                priority=PRIORITY_HIGH
            )

    def _publish_status(self):
        if self.bus:
            avg = self._total_planning_time / max(self._total_planned, 1)
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="planner_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "active_tasks": len(self._active_plans),
                    "queue_depth": len(self._task_queue),
                    "avg_planning_duration_ms": round(avg, 2)
                },
                priority=PRIORITY_NORMAL
            )

    def _send_plan_failed(self, session_id: str, intent_id: str, error_code: str, error_msg: str):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="plan_failed",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "intent_id": intent_id,
                    "error_code": error_code,
                    "error_msg": error_msg
                },
                priority=PRIORITY_NORMAL
            )

    # ====================== 队列与优先级 ======================
    def _enqueue_intent(self, intent: StructuredIntent):
        if len(self._task_queue) >= self.MAX_QUEUE_SIZE:
            lowest = max(self._task_queue, key=lambda i: i.priority)
            self._task_queue.remove(lowest)
            logger.warning(
                f"任务队列已满，丢弃最低优先级任务，intent_id: {lowest.intent_id}, "
                f"优先级: {lowest.priority}, 类型: {lowest.task_type.value}"
            )
        self._task_queue.append(intent)
        self._task_queue.sort(key=lambda i: (i.priority, i.timestamp))
        logger.info(f"任务入队成功，intent_id: {intent.intent_id}, 队列深度: {len(self._task_queue)}")

    # ====================== 异常恢复 ======================
    def _generate_recovery(self, plan: TaskPlan, receipt: Dict) -> Dict:
        error_code = receipt.get("error_code", "")
        alt_steps = []
        if error_code in ("TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED"):
            alt_steps = [{"description": "自动重试当前步骤", "tool_type": plan.steps[plan.current_step_index].required_tool_type}]
        return {
            "original_plan_id": plan.plan_id,
            "failed_step_id": receipt.get("step_id"),
            "alternative_steps": alt_steps,
            "rollback_steps": []
        }

    def emergency_shutdown(self):
        self.state = PlannerState.SYSTEM_PAUSED
        logger.info("任务规划模块已暂停")

    def get_state(self) -> PlannerState:
        return self.state

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_planned": self._total_planned,
            "avg_planning_time_ms": self._total_planning_time / max(self._total_planned, 1),
            "active_tasks": len(self._active_plans),
            "queue_depth": len(self._task_queue),
            "current_state": self.state.value
        }