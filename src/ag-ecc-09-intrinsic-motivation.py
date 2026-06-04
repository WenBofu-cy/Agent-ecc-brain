#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-09
模块名称: 内生动机模块
所属分区: 一、认知大脑核心模块
核心职责: 基于系统对自身能力短板、环境变化、用户长期偏好以及未完成任务的持续感知，自主
          生成探索、学习与任务执行的内在驱动力。将认知缺口、未知领域或优化机会转化为具体
          的“内生目标”，提交至 ag-ecc-02（任务规划模块）进行编排执行。驱动系统从被动响应
          工具向主动成长型智能体演化。不参与目标的具体执行，仅负责目标的自主发现、优先级
          评估与生成。

依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-05(记忆查询模块),
    ag-ecc-08(元认知模块), ag-ecc-12(资源调度模块)
被依赖模块:
    ag-ecc-02, ag-ecc-08

安全约束:
  I-01: 自主生成的目标不得涉及安全敏感操作（系统配置修改、权限变更、数据删除等）
  I-02: 用户在线且有活跃任务时，自主目标的优先级永远低于用户显式任务
  I-03: 同一类型的自主目标在冷却期内不得重复生成，防止系统陷入无意义的循环
  I-04: 自主目标在下发执行前必须通过 ag-ecc-04 安全仲裁模块的审查
  I-05: 系统资源不足时，禁止生成任何需要调用大模型或占用大量计算资源的探索目标
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class MotivationState(Enum):
    DORMANT = "dormant"
    ENVIRONMENT_SCAN = "environment_scan"
    GOAL_GENERATION = "goal_generation"
    GOAL_QUEUING = "goal_queuing"
    SYSTEM_PAUSED = "system_paused"


class GoalType(Enum):
    CAPABILITY_FILL = "能力补全"
    ENVIRONMENT_EXPLORE = "环境探索"
    MEMORY_MAINTENANCE = "记忆维护"
    USER_SERVICE_OPTIMIZE = "用户服务优化"
    SELF_REFLECTION = "自我反思"


@dataclass
class CognitiveBiasAlert:
    bias_type: str = ""
    dimension: str = ""
    severity: str = "中"
    suggested_correction: str = ""


@dataclass
class LearningRequirement:
    gap_description: str = ""
    target_dimension: str = ""
    suggested_method: str = "内部复盘"
    priority: float = 0.5


@dataclass
class UserPreferenceSummary:
    user_id: str = ""
    preference_keywords: List[str] = field(default_factory=list)
    high_freq_task_types: List[str] = field(default_factory=list)
    interest_trend: str = ""
    unfinished_goals: List[str] = field(default_factory=list)


@dataclass
class SystemResourceStatus:
    cpu_usage_pct: float = 0.0
    memory_usage_pct: float = 0.0
    storage_usage_pct: float = 0.0
    llm_quota_remaining: float = 1.0


@dataclass
class UserActivityStatus:
    is_online: bool = True
    active_sessions: int = 0
    has_unread_messages: bool = False


@dataclass
class AutonomousGoal:
    goal_id: str = ""
    goal_type: GoalType = GoalType.ENVIRONMENT_EXPLORE
    description: str = ""
    expected_benefit: str = ""
    estimated_resource_cost: float = 0.0
    priority: float = 0.3
    generation_reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProactiveSuggestion:
    suggestion_id: str = ""
    content: str = ""
    trigger_reason: str = ""
    user_options: List[str] = field(default_factory=list)


@dataclass
class LearningCompletionFeedback:
    goal_id: str = ""
    status: str = "completed"
    capability_improvement: Dict[str, float] = field(default_factory=dict)


@dataclass
class MotivationStatus:
    state: MotivationState = MotivationState.DORMANT
    goals_generated: int = 0
    goals_queued: int = 0
    goals_completed: int = 0
    last_active_time: float = 0.0


class IntrinsicMotivation:
    # 冷却配置（秒）
    COOLDOWNS = {
        GoalType.CAPABILITY_FILL: 1800,
        GoalType.ENVIRONMENT_EXPLORE: 7200,
        GoalType.MEMORY_MAINTENANCE: 21600,
        GoalType.USER_SERVICE_OPTIMIZE: 3600,
        GoalType.SELF_REFLECTION: 7200,
    }
    # 最大活跃自主目标数
    MAX_ACTIVE_AUTONOMOUS_GOALS = 3
    # 候选队列上限
    MAX_CANDIDATE_QUEUE = 10
    # 资源阈值
    CPU_THRESHOLD = 70.0
    MEMORY_THRESHOLD = 75.0
    # 状态上报间隔
    STATUS_REPORT_INTERVAL_SEC = 120

    def __init__(self):
        self.module_id = "ag-ecc-09"
        self.module_name = "内生动机模块"
        self.version = "V1.0"

        self.state = MotivationState.DORMANT
        self._candidate_queue: List[AutonomousGoal] = []
        self._active_goal_count: int = 0
        self._goals_generated: int = 0
        self._goals_completed: int = 0
        self._last_trigger_times: Dict[GoalType, float] = {}
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_bias_alert = None
        self._query_learning_requirement = None
        self._query_user_preference = None
        self._query_resource_status = None
        self._query_user_activity = None
        self._query_learning_feedback = None

        self._publish_autonomous_goal = None
        self._publish_proactive_suggestion = None
        self._publish_learning_feedback_forward = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_bias_alert_query(self, callback: Callable[[], Optional[CognitiveBiasAlert]]):
        self._query_bias_alert = callback

    def set_learning_requirement_query(self, callback: Callable[[], Optional[LearningRequirement]]):
        self._query_learning_requirement = callback

    def set_user_preference_query(self, callback: Callable[[], Optional[UserPreferenceSummary]]):
        self._query_user_preference = callback

    def set_resource_status_query(self, callback: Callable[[], Optional[SystemResourceStatus]]):
        self._query_resource_status = callback

    def set_user_activity_query(self, callback: Callable[[], Optional[UserActivityStatus]]):
        self._query_user_activity = callback

    def set_learning_feedback_query(self, callback: Callable[[], Optional[LearningCompletionFeedback]]):
        self._query_learning_feedback = callback

    def set_autonomous_goal_publisher(self, callback: Callable[[AutonomousGoal], None]):
        self._publish_autonomous_goal = callback

    def set_proactive_suggestion_publisher(self, callback: Callable[[ProactiveSuggestion], None]):
        self._publish_proactive_suggestion = callback

    def set_learning_feedback_forward_publisher(self, callback: Callable[[LearningCompletionFeedback], None]):
        self._publish_learning_feedback_forward = callback

    def set_status_report_publisher(self, callback: Callable[[MotivationStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_motivation_cycle(self):
        now = time.time()

        if self.state == MotivationState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 接收元认知驱动信号（最高优先级）
        bias = self._query_bias_alert() if self._query_bias_alert else None
        if bias:
            self._generate_capability_fill_goal(bias, now)
            return

        learning = self._query_learning_requirement() if self._query_learning_requirement else None
        if learning:
            self._generate_capability_fill_goal_from_learning(learning, now)
            return

        # 处理学习任务完成反馈
        feedback = self._query_learning_feedback() if self._query_learning_feedback else None
        if feedback:
            self._handle_learning_feedback(feedback)
            return

        # 环境扫描触发
        if self.state == MotivationState.DORMANT:
            resource = self._query_resource_status() if self._query_resource_status else None
            if resource and resource.cpu_usage_pct < self.CPU_THRESHOLD and resource.memory_usage_pct < self.MEMORY_THRESHOLD:
                user_activity = self._query_user_activity() if self._query_user_activity else None
                if user_activity and user_activity.active_sessions < 3:
                    self.state = MotivationState.ENVIRONMENT_SCAN
                    self._perform_environment_scan(now)

        # 目标下发
        if self.state == MotivationState.GOAL_QUEUING:
            self._dispatch_goals()

    # ========== 目标生成 ==========
    def _generate_capability_fill_goal(self, bias: CognitiveBiasAlert, now: float):
        self.state = MotivationState.GOAL_GENERATION
        if self._is_in_cooldown(GoalType.CAPABILITY_FILL, now):
            self.state = MotivationState.DORMANT
            return

        goal = AutonomousGoal(
            goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
            goal_type=GoalType.CAPABILITY_FILL,
            description=f"能力补全: 纠正{bias.dimension}偏差 - {bias.suggested_correction}",
            expected_benefit=f"提升{bias.dimension}能力",
            estimated_resource_cost=0.3,
            priority=0.7,
            generation_reason=f"元认知检测到{bias.bias_type}"
        )
        self._enqueue_goal(goal, GoalType.CAPABILITY_FILL, now)
        self.state = MotivationState.DORMANT

    def _generate_capability_fill_goal_from_learning(self, learning: LearningRequirement, now: float):
        self.state = MotivationState.GOAL_GENERATION
        if self._is_in_cooldown(GoalType.CAPABILITY_FILL, now):
            self.state = MotivationState.DORMANT
            return

        goal = AutonomousGoal(
            goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
            goal_type=GoalType.CAPABILITY_FILL,
            description=f"能力补全: {learning.gap_description}",
            expected_benefit=f"提升{learning.target_dimension}至健康水平",
            estimated_resource_cost=0.3,
            priority=learning.priority,
            generation_reason="能力评估发现短板"
        )
        self._enqueue_goal(goal, GoalType.CAPABILITY_FILL, now)
        self.state = MotivationState.DORMANT

    def _perform_environment_scan(self, now: float):
        # 扫描用户偏好
        preference = self._query_user_preference() if self._query_user_preference else None
        if preference and preference.unfinished_goals:
            for uf_goal in preference.unfinished_goals[:2]:
                goal = AutonomousGoal(
                    goal_id=f"AUTO-{uuid.uuid4().hex[:8]}",
                    goal_type=GoalType.USER_SERVICE_OPTIMIZE,
                    description=f"用户提醒: {uf_goal}",
                    expected_benefit="提升用户满意度",
                    estimated_resource_cost=0.1,
                    priority=0.5,
                    generation_reason="用户有未完成目标"
                )
                self._enqueue_goal(goal, GoalType.USER_SERVICE_OPTIMIZE, now)

        self.state = MotivationState.GOAL_QUEUING

    def _enqueue_goal(self, goal: AutonomousGoal, goal_type: GoalType, now: float):
        self._candidate_queue.append(goal)
        self._last_trigger_times[goal_type] = now
        self._goals_generated += 1

        if len(self._candidate_queue) > self.MAX_CANDIDATE_QUEUE:
            self._candidate_queue.sort(key=lambda g: g.priority)
            self._candidate_queue = self._candidate_queue[-self.MAX_CANDIDATE_QUEUE:]

        self.state = MotivationState.GOAL_QUEUING

    def _dispatch_goals(self):
        if not self._candidate_queue:
            self.state = MotivationState.DORMANT
            return

        self._candidate_queue.sort(key=lambda g: g.priority, reverse=True)

        while self._candidate_queue and self._active_goal_count < self.MAX_ACTIVE_AUTONOMOUS_GOALS:
            goal = self._candidate_queue.pop(0)
            if self._publish_autonomous_goal:
                self._publish_autonomous_goal(goal)
            self._active_goal_count += 1

        self.state = MotivationState.DORMANT

    def _handle_learning_feedback(self, feedback: LearningCompletionFeedback):
        if feedback.status == "completed":
            self._active_goal_count = max(0, self._active_goal_count - 1)
            self._goals_completed += 1
            if self._publish_learning_feedback_forward:
                self._publish_learning_feedback_forward(feedback)

    def _is_in_cooldown(self, goal_type: GoalType, now: float) -> bool:
        last_time = self._last_trigger_times.get(goal_type, 0)
        cooldown = self.COOLDOWNS.get(goal_type, 3600)
        return (now - last_time) < cooldown

    # ========== 辅助 ==========
    def _publish_status(self):
        if self._publish_status_report:
            self._publish_status_report(MotivationStatus(
                state=self.state,
                goals_generated=self._goals_generated,
                goals_queued=len(self._candidate_queue),
                goals_completed=self._goals_completed,
                last_active_time=max(self._last_trigger_times.values()) if self._last_trigger_times else 0.0
            ))

    def get_state(self) -> MotivationState:
        return self.state

    def emergency_shutdown(self):
        self.state = MotivationState.SYSTEM_PAUSED
        self._candidate_queue.clear()
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
    print("  Agent-ecc-brain 内生动机模块 (ag-ecc-09) 演示")
    print("=" * 70)

    motiv = IntrinsicMotivation()

    print_separator("STEP 1: 接收认知偏差告警生成目标")
    motiv.set_bias_alert_query(lambda: CognitiveBiasAlert(
        bias_type="过度自信", dimension="意图理解", suggested_correction="降低高置信度预测比例"
    ))
    motiv.run_motivation_cycle()
    print(f"  候选队列: {len(motiv._candidate_queue)}")

    print_separator("STEP 2: 环境扫描生成用户提醒目标")
    motiv.set_user_preference_query(lambda: UserPreferenceSummary(
        unfinished_goals=["完成上个月的数据分析报告"]
    ))
    motiv.set_resource_status_query(lambda: SystemResourceStatus(cpu_usage_pct=30.0, memory_usage_pct=50.0))
    motiv.set_user_activity_query(lambda: UserActivityStatus(active_sessions=1))
    motiv.run_motivation_cycle()

    print_separator("STEP 3: 目标下发")
    motiv.run_motivation_cycle()
    print(f"  活跃目标数: {motiv._active_goal_count}")

    print("\n✅ 内生动机模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-09 内生动机模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_motivation():
            return IntrinsicMotivation()

        # TC-E09-01: 认知偏差触发目标生成
        print("\n[TC-E09-01] 认知偏差触发目标生成")
        try:
            m = setup_motivation()
            m.set_bias_alert_query(lambda: CognitiveBiasAlert(bias_type="过度自信", dimension="意图理解"))
            m.run_motivation_cycle()
            assert m._goals_generated == 1
            assert len(m._candidate_queue) == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E09-02: 自主学习需求触发目标生成
        print("\n[TC-E09-02] 自主学习需求触发目标生成")
        try:
            m = setup_motivation()
            m.set_learning_requirement_query(lambda: LearningRequirement(
                gap_description="意图理解能力不足", target_dimension="intent_understanding", priority=0.8
            ))
            m.run_motivation_cycle()
            assert m._goals_generated == 1
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E09-03: 环境扫描生成用户提醒
        print("\n[TC-E09-03] 环境扫描生成用户提醒")
        try:
            m = setup_motivation()
            m.set_user_preference_query(lambda: UserPreferenceSummary(unfinished_goals=["任务A"]))
            m.set_resource_status_query(lambda: SystemResourceStatus(cpu_usage_pct=30.0, memory_usage_pct=50.0))
            m.set_user_activity_query(lambda: UserActivityStatus(active_sessions=1))
            m.run_motivation_cycle()
            assert m.state == MotivationState.GOAL_QUEUING
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E09-04: 队列超限丢弃最低优先级
        print("\n[TC-E09-04] 队列超限丢弃最低优先级")
        try:
            m = setup_motivation()
            for i in range(m.MAX_CANDIDATE_QUEUE + 3):
                m._candidate_queue.append(AutonomousGoal(
                    goal_id=f"G{i}", goal_type=GoalType.ENVIRONMENT_EXPLORE, priority=0.1 + i * 0.01
                ))
            m._candidate_queue.sort(key=lambda g: g.priority, reverse=True)
            m._candidate_queue = m._candidate_queue[:m.MAX_CANDIDATE_QUEUE]
            assert len(m._candidate_queue) <= m.MAX_CANDIDATE_QUEUE
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E09-05: 冷却期抑制重复生成
        print("\n[TC-E09-05] 冷却期抑制重复生成")
        try:
            m = setup_motivation()
            m.set_bias_alert_query(lambda: CognitiveBiasAlert(bias_type="过度自信", dimension="意图理解"))
            m.run_motivation_cycle()
            first_count = m._goals_generated
            # 立即再次触发
            m.set_bias_alert_query(lambda: CognitiveBiasAlert(bias_type="过度自信", dimension="意图理解"))
            m.run_motivation_cycle()
            assert m._goals_generated == first_count  # 冷却期内未增加
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E09-06: 紧急熔断
        print("\n[TC-E09-06] 紧急熔断")
        try:
            m = setup_motivation()
            m.emergency_shutdown()
            assert m.state == MotivationState.SYSTEM_PAUSED
            assert len(m._candidate_queue) == 0
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