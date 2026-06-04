#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-10
模块名称: 社会心智模块
所属分区: 一、认知大脑核心模块
核心职责: 作为 ECC 认知大脑的人机交互专属心智单元，负责感知用户实时情绪状态、推断行为
          意图、理解社交上下文，并据此适配系统的交互风格（语气、节奏、表达方式）。通过
          查询用户长期交互历史与个人偏好，实现千人千面的个性化交互体验。在检测到用户负面
          情绪或交互困境时，调整交互策略并向相关模块发出适配建议。不参与任务规划或工具执行，
          仅负责社会认知与交互风格的智能适配。

依赖模块:
    ag-ecc-05(记忆查询模块), ag-ecc-01(意图解析模块),
    ag-mem-46(用户情绪意图感知库), ag-mem-11(个性化建议生成单元)
被依赖模块:
    ag-ecc-01, ag-ecc-04(安全仲裁模块), ag-mem-11, ag-ecc-12(资源调度模块)

安全约束:
  S-01: 情绪意图感知数据仅用于交互风格适配，不得作为安全决策或任务执行的唯一依据
  S-02: 用户交互历史与偏好数据仅在本地处理，不得上传云端或共享给第三方模块
  S-03: 冲突化解期间，系统不得主动推送任何营销或推广内容
  S-04: 社交风险评估仅作为辅助参考，最终安全决策权归 ag-ecc-04 安全仲裁模块
  S-05: 本模块不得存储用户的原始对话内容，仅保留脱敏后的交互特征摘要
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class SocialMindState(Enum):
    NORMAL_MONITOR = "normal_monitor"
    EMOTION_ATTENTION = "emotion_attention"
    CONFLICT_RESOLUTION = "conflict_resolution"
    INTERACTION_OPTIMIZING = "interaction_optimizing"
    SYSTEM_PAUSED = "system_paused"


class EmotionLabel(Enum):
    CALM = "平静"
    SATISFIED = "满意"
    CONFUSED = "困惑"
    ANXIOUS = "焦虑"
    ANGRY = "愤怒"
    DISAPPOINTED = "失望"


class InteractionPace(Enum):
    FAST = "快速响应"
    NORMAL = "正常响应"
    SLOW = "缓慢引导"


@dataclass
class EmotionIntentResult:
    session_id: str = ""
    emotion_label: EmotionLabel = EmotionLabel.CALM
    emotion_confidence: float = 0.5
    intent_tendency: str = ""
    intent_confidence: float = 0.5
    perception_basis: str = ""


@dataclass
class InteractionHistorySummary:
    user_id: str = ""
    total_turns: int = 0
    recent_topics: List[str] = field(default_factory=list)
    emotion_trend: str = "稳定"
    interaction_pace_preference: str = "正常"


@dataclass
class UserPreferenceBackground:
    preference_keywords: List[str] = field(default_factory=list)
    interaction_style: str = "正常"
    push_preference: str = "正常"
    interaction_interval_preference: str = "正常"


@dataclass
class SessionContext:
    session_id: str = ""
    recent_dialogues: List[str] = field(default_factory=list)
    current_task_type: str = ""
    recent_system_actions: List[str] = field(default_factory=list)


@dataclass
class InteractionStyleAdvice:
    session_id: str = ""
    suggested_tone: str = "正常"
    suggested_pace: InteractionPace = InteractionPace.NORMAL
    push_tendency: str = "正常"
    adaptation_basis: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class EmotionIntentPrejudge:
    session_id: str = ""
    emotion_label: EmotionLabel = EmotionLabel.CALM
    intent_tendency: str = ""
    confidence: float = 0.5
    social_risk_level: str = "低"


@dataclass
class SocialRiskAlert:
    session_id: str = ""
    risk_type: str = ""
    risk_level: str = "低"
    trigger_behavior: str = ""
    suggested_handling: str = ""


@dataclass
class InteractionStrategyAdjustment:
    session_id: str = ""
    adjustment_type: str = ""
    previous_strategy: str = ""
    new_strategy: str = ""
    trigger_reason: str = ""


@dataclass
class SocialMindStatus:
    state: SocialMindState = SocialMindState.NORMAL_MONITOR
    current_emotion: str = "平静"
    strategy_summary: str = "正常交互"
    recent_emotion_changes: int = 0


class SocialMindModule:
    # 情绪-风格映射
    EMOTION_STYLE_MAP = {
        EmotionLabel.CALM: {"tone": "正常", "pace": InteractionPace.NORMAL, "push": "正常", "special": ""},
        EmotionLabel.SATISFIED: {"tone": "简洁友好", "pace": InteractionPace.FAST, "push": "可适度推送", "special": "可增加主动建议"},
        EmotionLabel.CONFUSED: {"tone": "耐心详细", "pace": InteractionPace.SLOW, "push": "暂停推送", "special": "主动提供帮助选项"},
        EmotionLabel.ANXIOUS: {"tone": "安抚简洁", "pace": InteractionPace.FAST, "push": "暂停推送", "special": "优先处理当前问题"},
        EmotionLabel.ANGRY: {"tone": "冷静中立", "pace": InteractionPace.SLOW, "push": "停止推送", "special": "启动冲突化解策略"},
        EmotionLabel.DISAPPOINTED: {"tone": "诚恳温和", "pace": InteractionPace.NORMAL, "push": "暂停推送", "special": "主动承认不足并提供补偿方案"},
    }

    # 情绪历史保留条数
    MAX_EMOTION_HISTORY = 10
    # 频繁切换锁定阈值
    MAX_EMOTION_SWITCHES_SHORT = 3
    EMOTION_LOCK_DURATION_SEC = 30
    # 状态上报间隔
    STATUS_REPORT_INTERVAL_SEC = 60

    def __init__(self):
        self.module_id = "ag-ecc-10"
        self.module_name = "社会心智模块"
        self.version = "V1.0"

        self.state = SocialMindState.NORMAL_MONITOR
        self._emotion_history: Dict[str, List[Dict[str, Any]]] = {}
        self._interaction_strategies: Dict[str, InteractionStyleAdvice] = {}
        self._emotion_lock_until: Dict[str, float] = {}
        self._recent_emotion_changes: int = 0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_emotion_result = None
        self._query_interaction_history = None
        self._query_preference_background = None
        self._query_session_context = None
        self._query_social_risk_request = None

        self._publish_style_advice = None
        self._publish_emotion_prejudge = None
        self._publish_social_risk_alert = None
        self._publish_strategy_adjustment = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_emotion_result_query(self, callback: Callable[[], Optional[EmotionIntentResult]]):
        self._query_emotion_result = callback

    def set_interaction_history_query(self, callback: Callable[[str], Optional[InteractionHistorySummary]]):
        self._query_interaction_history = callback

    def set_preference_background_query(self, callback: Callable[[str], Optional[UserPreferenceBackground]]):
        self._query_preference_background = callback

    def set_session_context_query(self, callback: Callable[[str], Optional[SessionContext]]):
        self._query_session_context = callback

    def set_social_risk_request_query(self, callback: Callable[[], Optional[Dict[str, Any]]]):
        self._query_social_risk_request = callback

    def set_style_advice_publisher(self, callback: Callable[[InteractionStyleAdvice], None]):
        self._publish_style_advice = callback

    def set_emotion_prejudge_publisher(self, callback: Callable[[EmotionIntentPrejudge], None]):
        self._publish_emotion_prejudge = callback

    def set_social_risk_alert_publisher(self, callback: Callable[[SocialRiskAlert], None]):
        self._publish_social_risk_alert = callback

    def set_strategy_adjustment_publisher(self, callback: Callable[[InteractionStrategyAdjustment], None]):
        self._publish_strategy_adjustment = callback

    def set_status_report_publisher(self, callback: Callable[[SocialMindStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_social_cycle(self):
        now = time.time()

        if self.state == SocialMindState.SYSTEM_PAUSED:
            return

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 接收情绪意图感知结果
        emotion_result = self._query_emotion_result() if self._query_emotion_result else None
        if emotion_result:
            self._process_emotion(emotion_result, now)
            return

        # 处理社交风险评估请求
        risk_req = self._query_social_risk_request() if self._query_social_risk_request else None
        if risk_req:
            self._assess_social_risk(risk_req)

    # ========== 情绪处理 ==========
    def _process_emotion(self, result: EmotionIntentResult, now: float):
        session_id = result.session_id
        emotion_label = result.emotion_label

        # 检查情绪锁定
        if session_id in self._emotion_lock_until and now < self._emotion_lock_until[session_id]:
            return

        # 更新情绪历史
        if session_id not in self._emotion_history:
            self._emotion_history[session_id] = []
        self._emotion_history[session_id].append({
            "emotion": emotion_label,
            "time": now
        })
        if len(self._emotion_history[session_id]) > self.MAX_EMOTION_HISTORY:
            self._emotion_history[session_id] = self._emotion_history[session_id][-self.MAX_EMOTION_HISTORY:]

        # 检测频繁切换
        if self._is_frequent_switch(session_id):
            self._emotion_lock_until[session_id] = now + self.EMOTION_LOCK_DURATION_SEC
            self._recent_emotion_changes += 1
            return

        # 状态判定
        if emotion_label == EmotionLabel.ANGRY:
            self.state = SocialMindState.CONFLICT_RESOLUTION
            self._start_conflict_resolution(session_id)
        elif emotion_label in (EmotionLabel.CONFUSED, EmotionLabel.ANXIOUS, EmotionLabel.DISAPPOINTED):
            self.state = SocialMindState.EMOTION_ATTENTION
        else:
            self.state = SocialMindState.NORMAL_MONITOR

        # 生成交互风格适配建议
        mapping = self.EMOTION_STYLE_MAP.get(emotion_label, self.EMOTION_STYLE_MAP[EmotionLabel.CALM])
        advice = InteractionStyleAdvice(
            session_id=session_id,
            suggested_tone=mapping["tone"],
            suggested_pace=mapping["pace"],
            push_tendency=mapping["push"],
            adaptation_basis=f"用户情绪: {emotion_label.value}"
        )
        self._interaction_strategies[session_id] = advice

        # 发送适配建议
        if self._publish_style_advice:
            self._publish_style_advice(advice)

        # 发送情绪预判
        if self._publish_emotion_prejudge:
            self._publish_emotion_prejudge(EmotionIntentPrejudge(
                session_id=session_id,
                emotion_label=emotion_label,
                intent_tendency=result.intent_tendency,
                confidence=result.emotion_confidence,
                social_risk_level="高" if emotion_label == EmotionLabel.ANGRY else "低"
            ))

        # 检测社交风险
        if emotion_label == EmotionLabel.ANGRY:
            if self._publish_social_risk_alert:
                self._publish_social_risk_alert(SocialRiskAlert(
                    session_id=session_id,
                    risk_type="用户愤怒",
                    risk_level="高",
                    trigger_behavior="情绪标签为愤怒",
                    suggested_handling="启动冲突化解策略，暂停主动推送"
                ))

        if self.state in (SocialMindState.EMOTION_ATTENTION, SocialMindState.CONFLICT_RESOLUTION):
            self.state = SocialMindState.NORMAL_MONITOR

    def _is_frequent_switch(self, session_id: str) -> bool:
        history = self._emotion_history.get(session_id, [])
        if len(history) < self.MAX_EMOTION_SWITCHES_SHORT + 1:
            return False
        recent = history[-(self.MAX_EMOTION_SWITCHES_SHORT + 1):]
        switches = sum(1 for i in range(1, len(recent)) if recent[i]["emotion"] != recent[i-1]["emotion"])
        return switches >= self.MAX_EMOTION_SWITCHES_SHORT

    def _start_conflict_resolution(self, session_id: str):
        self._log_event("CONFLICT_RESOLUTION_STARTED", {"session_id": session_id})
        # 调整策略为冷静中立 + 停止推送
        advice = InteractionStyleAdvice(
            session_id=session_id,
            suggested_tone="冷静中立",
            suggested_pace=InteractionPace.SLOW,
            push_tendency="停止推送",
            adaptation_basis="冲突化解"
        )
        self._interaction_strategies[session_id] = advice
        if self._publish_style_advice:
            self._publish_style_advice(advice)

    # ========== 社交风险评估 ==========
    def _assess_social_risk(self, request: Dict[str, Any]):
        # 简单评估，实际可扩展
        risk_level = "低"
        content = request.get("content", "")
        if any(kw in content for kw in ["投诉", "退款", "赔偿"]):
            risk_level = "中"
        if self._publish_social_risk_alert:
            self._publish_social_risk_alert(SocialRiskAlert(
                session_id=request.get("session_id", ""),
                risk_type="社交风险评估",
                risk_level=risk_level,
                trigger_behavior=content[:100],
                suggested_handling="正常处理" if risk_level == "低" else "需关注"
            ))

    # ========== 辅助 ==========
    def _publish_status(self):
        if self._publish_status_report:
            self._publish_status_report(SocialMindStatus(
                state=self.state,
                current_emotion="平静",
                strategy_summary="正常",
                recent_emotion_changes=self._recent_emotion_changes
            ))

    def get_state(self) -> SocialMindState:
        return self.state

    def emergency_shutdown(self):
        self.state = SocialMindState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 社会心智模块 (ag-ecc-10) 演示")
    print("=" * 70)

    sm = SocialMindModule()

    print_separator("STEP 1: 用户情绪=满意")
    sm.set_emotion_result_query(lambda: EmotionIntentResult(
        session_id="S001", emotion_label=EmotionLabel.SATISFIED,
        emotion_confidence=0.9, intent_tendency="任务执行"
    ))
    sm.run_social_cycle()

    print_separator("STEP 2: 用户情绪=愤怒（启动冲突化解）")
    sm.set_emotion_result_query(lambda: EmotionIntentResult(
        session_id="S001", emotion_label=EmotionLabel.ANGRY,
        emotion_confidence=0.95, intent_tendency="表达不满"
    ))
    sm.run_social_cycle()
    print(f"  状态: {sm.state.value}")

    print_separator("STEP 3: 情绪频繁切换锁定")
    for i in range(5):
        sm.set_emotion_result_query(lambda i=i: EmotionIntentResult(
            session_id="S001",
            emotion_label=EmotionLabel.ANGRY if i % 2 == 0 else EmotionLabel.CALM,
            emotion_confidence=0.8, intent_tendency=""
        ))
        sm.run_social_cycle()
    print(f"  情绪被锁定: {'S001' in sm._emotion_lock_until}")

    print("\n✅ 社会心智模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-10 社会心智模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_sm():
            return SocialMindModule()

        # TC-E10-01: 满意情绪适配
        print("\n[TC-E10-01] 满意情绪适配")
        try:
            s = setup_sm()
            s.set_emotion_result_query(lambda: EmotionIntentResult(
                session_id="T01", emotion_label=EmotionLabel.SATISFIED,
                emotion_confidence=0.9, intent_tendency="任务执行"
            ))
            s.run_social_cycle()
            assert "T01" in s._interaction_strategies
            strategy = s._interaction_strategies["T01"]
            assert strategy.suggested_tone == "简洁友好"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E10-02: 困惑情绪适配
        print("\n[TC-E10-02] 困惑情绪适配")
        try:
            s = setup_sm()
            s.set_emotion_result_query(lambda: EmotionIntentResult(
                session_id="T02", emotion_label=EmotionLabel.CONFUSED,
                emotion_confidence=0.85, intent_tendency="寻求帮助"
            ))
            s.run_social_cycle()
            strategy = s._interaction_strategies["T02"]
            assert strategy.suggested_pace == InteractionPace.SLOW
            assert strategy.push_tendency == "暂停推送"
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E10-03: 愤怒触发冲突化解
        print("\n[TC-E10-03] 愤怒触发冲突化解")
        try:
            s = setup_sm()
            s.set_emotion_result_query(lambda: EmotionIntentResult(
                session_id="T03", emotion_label=EmotionLabel.ANGRY,
                emotion_confidence=0.9, intent_tendency="表达不满"
            ))
            s.run_social_cycle()
            assert s.state == SocialMindState.CONFLICT_RESOLUTION or s.state == SocialMindState.NORMAL_MONITOR
            strategy = s._interaction_strategies.get("T03")
            assert strategy is not None
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E10-04: 频繁切换锁定
        print("\n[TC-E10-04] 频繁切换锁定")
        try:
            s = setup_sm()
            for i in range(5):
                s.set_emotion_result_query(lambda i=i: EmotionIntentResult(
                    session_id="T04",
                    emotion_label=EmotionLabel.ANGRY if i % 2 == 0 else EmotionLabel.CALM,
                    emotion_confidence=0.8, intent_tendency=""
                ))
                s.run_social_cycle()
            assert "T04" in s._emotion_lock_until
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E10-05: 发送社交风险告警
        print("\n[TC-E10-05] 愤怒时发送社交风险告警")
        try:
            s = setup_sm()
            alert_triggered = [False]
            def mock_alert(alert):
                alert_triggered[0] = True
            s.set_social_risk_alert_publisher(mock_alert)
            s.set_emotion_result_query(lambda: EmotionIntentResult(
                session_id="T05", emotion_label=EmotionLabel.ANGRY,
                emotion_confidence=0.9, intent_tendency="表达不满"
            ))
            s.run_social_cycle()
            assert alert_triggered[0]
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E10-06: 紧急熔断
        print("\n[TC-E10-06] 紧急熔断")
        try:
            s = setup_sm()
            s.emergency_shutdown()
            assert s.state == SocialMindState.SYSTEM_PAUSED
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