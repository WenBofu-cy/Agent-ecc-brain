#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-09
模块名称: 内生动机模块
所属分区: 一、认知大脑核心模块
版本：V1.0（优先级合规版）
原创提出者：文波福

核心职责:
  基于能力短板、环境变化、用户长期偏好及未完成任务，自主生成探索、学习与
  任务执行的内在驱动力。将认知缺口转化为“内生目标”，提交至 ag-ecc-02 编排执行。
  不参与目标的具体执行，仅负责目标的自主发现、优先级评估与生成。

依赖模块: ag-ecc-02, ag-ecc-05, ag-ecc-08, ag-ecc-12
被依赖模块: ag-ecc-02, ag-ecc-08

安全约束:
  I-01: 自主生成的目标不得涉及安全敏感操作
  I-02: 用户在线且有活跃任务时，自主目标优先级永远低于用户显式任务
  I-03: 同一类型的自主目标在冷却期内不得重复生成
  I-04: 自主目标下发前必须通过 ag-ecc-04 安全仲裁模块的审查（由下游保证）
  I-05: 系统资源不足时禁止生成需大模型或大量计算资源的探索目标
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_HIGH, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-09")


# ==================== 状态枚举：大写合规（CPEC 标准）====================
class MotivationState(Enum):
    DORMANT = "DORMANT"
    ENVIRONMENT_SCAN = "ENVIRONMENT_SCAN"
    GOAL_GENERATION = "GOAL_GENERATION"
    GOAL_QUEUING = "GOAL_QUEUING"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"


class GoalType(Enum):
    CAPABILITY_FILL = "能力补全"
    ENVIRONMENT_EXPLORE = "环境探索"
    MEMORY_MAINTENANCE = "记忆维护"
    USER_SERVICE_OPTIMIZE = "用户服务优化"
    SELF_REFLECTION = "自我反思"


@dataclass
class AutonomousGoal:
    goal_id: str = ""
    goal_type: GoalType = GoalType.ENVIRONMENT_EXPLORE
    description: str = ""
    expected_benefit: str = ""
    estimated_resource_cost: float = 0.0
    priority: float = 10.0          # 数值越大优先级越低，确保低于用户任务 (默认5)
    generation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal_type": self.goal_type.value,
            "description": self.description,
            "expected_benefit": self.expected_benefit,
            "estimated_resource_cost": self.estimated_resource_cost,
            "priority": self.priority,
            "generation_reason": self.generation_reason,
        }


class IntrinsicMotivation:
    # 各类型目标的冷却时间（秒）
    COOLDOWNS = {
        GoalType.CAPABILITY_FILL: 1800,
        GoalType.ENVIRONMENT_EXPLORE: 7200,
        GoalType.MEMORY_MAINTENANCE: 21600,
        GoalType.USER_SERVICE_OPTIMIZE: 3600,
        GoalType.SELF_REFLECTION: 7200,
    }
    MAX_ACTIVE_AUTONOMOUS_GOALS = 3
    MAX_CANDIDATE_QUEUE = 10
    CPU_THRESHOLD = 70.0
    MEMORY_THRESHOLD = 75.0
    STATUS_REPORT_INTERVAL_SEC = 120

    # 自主目标优先级常量（数值越大优先级越低，用户任务优先级通常为5）
    AUTONOMOUS_PRIORITY = 9.0

    def __init__(self):
        self.module_id = "ag-ecc-09"
        self.version = "V1.0"
        self.state = MotivationState.DORMANT
        self.bus = None  # 由主入口注入 InternalBus

        self._candidate_queue: List[AutonomousGoal] = []
        self._active_goal_count = 0
        self._goals_generated = 0
        self._goals_completed = 0
        self._last_trigger_times: Dict[GoalType, float] = {}
        self._last_status_time = time.time()

        # 消息缓冲区
        self._bias_alerts: List[Dict] = []
        self._learning_requirements: List[Dict] = []
        self._user_preferences: List[Dict] = []
        self._learning_feedbacks: List[Dict] = []

        logger.info("✅ 内生动机模块初始化完成")

    # ====================== 总线消息入口 ======================
    def handle_message(self, msg: Message):
        """接收总线消息"""
        try:
            topic = msg.topic

            if topic == "ag-ecc-09.bias_alert":
                self._bias_alerts.append(msg.data)
            elif topic == "ag-ecc-09.learning_requirement":
                self._learning_requirements.append(msg.data)
            elif topic == "ag-ecc-09.user_preference":
                self._user_preferences.append(msg.data)
            elif topic == "ag-ecc-09.learning_feedback":
                self._learning_feedbacks.append(msg.data)

            # ==================== 修复：全局暂停 / 关闭 ====================
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-09.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()

            elif topic == "ag-ecc-12.resume":
                if self.state == MotivationState.SYSTEM_PAUSED:
                    self.state = MotivationState.DORMANT
                    logger.info("▶️ 内生动机模块已恢复服务")

        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    # ====================== CPEC 主循环 ======================
    def intrinsic_motivation_main_loop(self):
        if self.state == MotivationState.SYSTEM_PAUSED:
            return

        now = time.time()

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理偏差告警
        while self._bias_alerts:
            self._generate_from_bias(self._bias_alerts.pop(0), now)

        # 处理学习需求
        while self._learning_requirements:
            self._generate_from_learning(self._learning_requirements.pop(0), now)

        # 处理学习反馈
        while self._learning_feedbacks:
            self._handle_feedback(self._learning_feedbacks.pop(0))

        # 环境扫描
        self._try_environment_scan(now)

        # 目标下发
        if self.state == MotivationState.GOAL_QUEUING:
            self._dispatch_goals()

    # ====================== 目标生成 ======================
    def _generate_from_bias(self, data: Dict, now: float):
        if self._is_in_cooldown(GoalType.CAPABILITY_FILL, now):
            return
        goal = AutonomousGoal(
            goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
            goal_type=GoalType.CAPABILITY_FILL,
            description=f"纠正{data.get('dimension','')}偏差: {data.get('suggested_correction','')}",
            expected_benefit=f"提升{data.get('dimension','')}能力",
            estimated_resource_cost=0.3,
            priority=self.AUTONOMOUS_PRIORITY,
            generation_reason=f"元认知检测到{data.get('bias_type','')}"
        )
        self._enqueue(goal, GoalType.CAPABILITY_FILL, now)

    def _generate_from_learning(self, data: Dict, now: float):
        if self._is_in_cooldown(GoalType.CAPABILITY_FILL, now):
            return
        goal = AutonomousGoal(
            goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
            goal_type=GoalType.CAPABILITY_FILL,
            description=data.get("gap_description", ""),
            expected_benefit=f"提升{data.get('target_dimension','')}",
            estimated_resource_cost=0.3,
            priority=self.AUTONOMOUS_PRIORITY,
            generation_reason="能力评估发现短板"
        )
        self._enqueue(goal, GoalType.CAPABILITY_FILL, now)

    def _try_environment_scan(self, now: float):
        if self.state != MotivationState.DORMANT:
            return
        # 资源检查：通过总线同步请求 ag-ecc-12
        if not self._resources_sufficient():
            return
        self.state = MotivationState.ENVIRONMENT_SCAN
        # 处理缓存的用户偏好
        while self._user_preferences:
            pref = self._user_preferences.pop(0)
            for uf_goal in pref.get("unfinished_goals", [])[:2]:
                goal = AutonomousGoal(
                    goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
                    goal_type=GoalType.USER_SERVICE_OPTIMIZE,
                    description=f"用户提醒: {uf_goal}",
                    expected_benefit="提升用户满意度",
                    estimated_resource_cost=0.1,
                    priority=self.AUTONOMOUS_PRIORITY,
                    generation_reason="用户有未完成目标"
                )
                self._enqueue(goal, GoalType.USER_SERVICE_OPTIMIZE, now)
                # 向用户交互层发送主动建议
                self._publish_proactive_suggestion(goal)
        self.state = MotivationState.GOAL_QUEUING

    def _resources_sufficient(self) -> bool:
        if not self.bus:
            return False
        resp = self.bus.request(
            topic="ag-ecc-12.query_resource",
            source_module=self.module_id,
            target_module="ag-ecc-12",
            data={},
            timeout_ms=1000
        )
        if resp and resp.data:
            cpu = resp.data.get("cpu_usage_pct", 100)
            mem = resp.data.get("memory_usage_pct", 100)
            active_sessions = resp.data.get("active_sessions", 0)
            # 用户在线且有活跃任务时，降低自主目标生成意愿
            if active_sessions > 0:
                return False
            return cpu < self.CPU_THRESHOLD and mem < self.MEMORY_THRESHOLD
        return False

    def _enqueue(self, goal: AutonomousGoal, goal_type: GoalType, now: float):
        self._candidate_queue.append(goal)
        self._last_trigger_times[goal_type] = now
        self._goals_generated += 1
        if len(self._candidate_queue) > self.MAX_CANDIDATE_QUEUE:
            # 按优先级数值升序保留（数值越小越优先）
            self._candidate_queue.sort(key=lambda g: g.priority)
            self._candidate_queue = self._candidate_queue[:self.MAX_CANDIDATE_QUEUE]
        self.state = MotivationState.GOAL_QUEUING

    def _dispatch_goals(self):
        if not self._candidate_queue:
            self.state = MotivationState.DORMANT
            return
        # 按优先级数值升序（越小越优先）确保低优先级的先出
        self._candidate_queue.sort(key=lambda g: g.priority)
        while self._candidate_queue and self._active_goal_count < self.MAX_ACTIVE_AUTONOMOUS_GOALS:
            goal = self._candidate_queue.pop(0)
            if self.bus:
                # 注意：安全仲裁由下游 ag-ecc-02 调用 ag-ecc-04 完成，本模块仅生成目标
                self.bus.publish_to_module(
                    target_module="ag-ecc-02",
                    event_type="autonomous_task",
                    source_module=self.module_id,
                    data=goal.to_dict(),
                    priority=PRIORITY_NORMAL
                )
            self._active_goal_count += 1
        self.state = MotivationState.DORMANT

    def _handle_feedback(self, data: Dict):
        if data.get("status") == "completed":
            self._active_goal_count = max(0, self._active_goal_count - 1)
            self._goals_completed += 1
            if self.bus:
                self.bus.publish_to_module(
                    target_module="ag-ecc-08",
                    event_type="learning_feedback",
                    source_module=self.module_id,
                    data=data,
                    priority=PRIORITY_LOW
                )

    def _is_in_cooldown(self, goal_type: GoalType, now: float) -> bool:
        last = self._last_trigger_times.get(goal_type, 0)
        return (now - last) < self.COOLDOWNS.get(goal_type, 3600)

    def _publish_proactive_suggestion(self, goal: AutonomousGoal):
        """向用户发送主动建议"""
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="proactive_suggestion",
                source_module=self.module_id,
                data={
                    "suggestion_id": f"SUG-{uuid.uuid4().hex[:8]}",
                    "description": goal.description,
                    "trigger_reason": goal.generation_reason,
                    "user_options": ["立即执行", "稍后提醒", "忽略"]
                },
                priority=PRIORITY_LOW
            )

    def _publish_status(self):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="motivation_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "goals_generated": self._goals_generated,
                    "goals_queued": len(self._candidate_queue),
                    "goals_completed": self._goals_completed,
                },
                priority=PRIORITY_LOW
            )

    def emergency_shutdown(self):
        self.state = MotivationState.SYSTEM_PAUSED
        self._candidate_queue.clear()
        logger.info("⏹️ 内生动机模块已暂停（系统熔断）")

    def get_state(self) -> MotivationState:
        return self.state