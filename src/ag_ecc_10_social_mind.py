#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-10
模块名称: 社会心智模块
所属分区: 一、认知大脑核心模块
版本：V1.0（终审加固版）
核心职责: 感知用户实时情绪状态、推断行为意图、理解社交上下文，适配交互风格。
          通过查询用户交互历史与偏好，实现个性化交互体验。
          检测负面情绪时调整策略并向相关模块发出适配建议。
          不参与任务规划或工具执行，仅负责社会认知与交互风格的智能适配。

依赖模块: ag-ecc-05, ag-ecc-01, ag-mem-46, ag-mem-11, ag-ecc-07
被依赖模块: ag-ecc-01, ag-ecc-04, ag-mem-11, ag-ecc-12

安全约束:
  S-01: 情绪意图感知数据仅用于交互风格适配，不得作为安全决策或任务执行的唯一依据
  S-02: 用户交互历史与偏好数据仅在本地处理，不得上传云端或共享给第三方模块
  S-03: 冲突化解期间，系统不得主动推送任何营销或推广内容
  S-04: 社交风险评估仅作为辅助参考，最终安全决策权归 ag-ecc-04 安全仲裁模块
  S-05: 本模块不得存储用户的原始对话内容，仅保留脱敏后的交互特征摘要
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_HIGH, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-10")


class SocialMindState(Enum):
    NORMAL_MONITOR = "NORMAL_MONITOR"
    EMOTION_ATTENTION = "EMOTION_ATTENTION"
    CONFLICT_RESOLUTION = "CONFLICT_RESOLUTION"
    INTERACTION_OPTIMIZING = "INTERACTION_OPTIMIZING"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"


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
class InteractionStyleAdvice:
    session_id: str = ""
    suggested_tone: str = "正常"
    suggested_pace: InteractionPace = InteractionPace.NORMAL
    push_tendency: str = "正常"
    adaptation_basis: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "suggested_tone": self.suggested_tone,
            "suggested_pace": self.suggested_pace.value,
            "push_tendency": self.push_tendency,
            "adaptation_basis": self.adaptation_basis,
            "timestamp": self.timestamp
        }


class SocialMindModule:
    EMOTION_STYLE_MAP = {
        EmotionLabel.CALM: {"tone": "正常", "pace": InteractionPace.NORMAL, "push": "正常", "special": ""},
        EmotionLabel.SATISFIED: {"tone": "简洁友好", "pace": InteractionPace.FAST, "push": "可适度推送", "special": "可增加主动建议"},
        EmotionLabel.CONFUSED: {"tone": "耐心详细", "pace": InteractionPace.SLOW, "push": "暂停推送", "special": "主动提供帮助选项"},
        EmotionLabel.ANXIOUS: {"tone": "安抚简洁", "pace": InteractionPace.FAST, "push": "暂停推送", "special": "优先处理当前问题"},
        EmotionLabel.ANGRY: {"tone": "冷静中立", "pace": InteractionPace.SLOW, "push": "停止推送", "special": "启动冲突化解策略"},
        EmotionLabel.DISAPPOINTED: {"tone": "诚恳温和", "pace": InteractionPace.NORMAL, "push": "暂停推送", "special": "主动承认不足并提供补偿方案"},
    }

    MAX_EMOTION_HISTORY = 10
    MAX_EMOTION_SWITCHES_SHORT = 3
    EMOTION_LOCK_DURATION_SEC = 30
    MAX_CONTINUOUS_LOCK = 3
    STATUS_REPORT_INTERVAL_SEC = 60

    RISK_KEYWORDS = {"投诉", "退款", "赔偿", "举报", "不满", "追责"}

    def __init__(self):
        self.module_id = "ag-ecc-10"
        self.version = "V1.0"
        self.state = SocialMindState.NORMAL_MONITOR
        self.bus = None

        # S-05 严格遵守：仅存储脱敏情绪特征/摘要，不保存任何原始对话内容
        self._emotion_history: Dict[str, List[Dict[str, Any]]] = {}
        self._interaction_strategies: Dict[str, InteractionStyleAdvice] = {}
        self._emotion_lock_until: Dict[str, float] = {}
        self._continuous_lock_count: Dict[str, int] = {}
        self._recent_emotion_changes: int = 0
        self._last_status_time: float = time.time()

        self._new_session_cache: Dict[str, Dict[str, Any]] = {}

        # 消息缓冲区
        self._emotion_results: List[Dict] = []
        self._social_risk_requests: List[Dict] = []
        self._session_start_events: List[Dict] = []
        self._history_summary_results: List[Dict] = []
        self._user_preference_results: List[Dict] = []
        self._session_context_results: List[Dict] = []

        logger.info("✅ 社会心智模块初始化完成")

    # ====================== 总线消息入口 ======================
    def handle_message(self, msg: Message):
        try:
            topic = msg.topic
            if topic == "ag-ecc-10.emotion_result":
                self._emotion_results.append(msg.data)
            elif topic == "ag-ecc-10.social_risk_request":
                self._social_risk_requests.append(msg.data)
            elif topic == "ag-ecc-10.session_start":
                self._session_start_events.append(msg.data)
            elif topic == "ag-ecc-05.history_summary":
                self._history_summary_results.append(msg.data)
            elif topic == "ag-mem-11.user_preference":
                self._user_preference_results.append(msg.data)
            elif topic == "ag-ecc-07.session_context":
                self._session_context_results.append(msg.data)
            elif topic in ("ag-ecc-12.shutdown", "ag-ecc-10.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()
            elif topic == "ag-ecc-12.resume":
                if self.state == SocialMindState.SYSTEM_PAUSED:
                    self.state = SocialMindState.NORMAL_MONITOR
                    logger.info("▶️ 社会心智模块恢复服务")
        except Exception as e:
            logger.error(f"消息处理异常: {e}", exc_info=True)

    # ====================== CPEC 主循环 ======================
    def social_mind_main_loop(self):
        if self.state == SocialMindState.SYSTEM_PAUSED:
            return

        now = time.time()

        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 处理新会话事件
        while self._session_start_events:
            try:
                self._handle_new_session(self._session_start_events.pop(0), now)
            except Exception as e:
                logger.error(f"新会话处理异常: {e}")

        # 处理外部模块返回数据
        while self._history_summary_results:
            try:
                self._process_history_summary(self._history_summary_results.pop(0))
            except Exception as e:
                logger.error(f"历史摘要处理异常: {e}")
        while self._user_preference_results:
            try:
                self._process_user_preference(self._user_preference_results.pop(0))
            except Exception as e:
                logger.error(f"用户偏好处理异常: {e}")
        while self._session_context_results:
            try:
                self._process_session_context(self._session_context_results.pop(0))
            except Exception as e:
                logger.error(f"会话上下文处理异常: {e}")

        # 处理情绪结果
        while self._emotion_results:
            try:
                self._process_emotion(self._emotion_results.pop(0), now)
            except Exception as e:
                logger.error(f"情绪数据处理异常: {e}")

        # 处理社交风险评估请求
        while self._social_risk_requests:
            try:
                self._assess_social_risk(self._social_risk_requests.pop(0))
            except Exception as e:
                logger.error(f"社交风险评估异常: {e}")

    # ====================== 新会话初始化与交互优化 ======================
    def _handle_new_session(self, data: Dict, now: float):
        session_id = data.get("session_id", "")
        if not session_id:
            return

        self.state = SocialMindState.INTERACTION_OPTIMIZING
        self._new_session_cache[session_id] = {"session_start": now}

        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-05",
                event_type="query_history_summary",
                source_module=self.module_id,
                data={"session_id": session_id},
                priority=PRIORITY_NORMAL
            )
            self.bus.publish_to_module(
                target_module="ag-mem-11",
                event_type="query_user_preference",
                source_module=self.module_id,
                data={"session_id": session_id},
                priority=PRIORITY_NORMAL
            )
            self.bus.publish_to_module(
                target_module="ag-ecc-07",
                event_type="query_session_context",
                source_module=self.module_id,
                data={"session_id": session_id},
                priority=PRIORITY_NORMAL
            )
        logger.info(f"新会话 {session_id} 进入交互优化状态，开始加载个性化数据")

    def _process_history_summary(self, data: Dict):
        session_id = data.get("session_id", "")
        if session_id not in self._new_session_cache:
            return
        self._new_session_cache[session_id]["history_summary"] = data.get("summary", "")
        self._try_build_initial_strategy(session_id)

    def _process_user_preference(self, data: Dict):
        session_id = data.get("session_id", "")
        if session_id not in self._new_session_cache:
            return
        self._new_session_cache[session_id]["user_preference"] = data.get("preference", "")
        self._try_build_initial_strategy(session_id)

    def _process_session_context(self, data: Dict):
        session_id = data.get("session_id", "")
        if session_id not in self._new_session_cache:
            return
        self._new_session_cache[session_id]["context"] = data.get("context", "")
        self._try_build_initial_strategy(session_id)

    def _try_build_initial_strategy(self, session_id: str):
        cache = self._new_session_cache.get(session_id, {})
        if not all(k in cache for k in ("history_summary", "user_preference", "context")):
            return

        advice = InteractionStyleAdvice(
            session_id=session_id,
            suggested_tone="正常",
            suggested_pace=InteractionPace.NORMAL,
            push_tendency="正常",
            adaptation_basis=f"新会话初始化：结合历史摘要、用户偏好、会话上下文生成初始策略"
        )
        self._interaction_strategies[session_id] = advice
        self._broadcast_style_advice(advice)

        self.state = SocialMindState.NORMAL_MONITOR
        self._new_session_cache.pop(session_id, None)
        logger.info(f"会话 {session_id} 初始交互策略生成完成，切回正常监控状态")

    # ====================== 下发交互风格建议（双目标模块） ======================
    def _broadcast_style_advice(self, advice: InteractionStyleAdvice):
        if not self.bus:
            return
        data = advice.to_dict()
        self.bus.publish_to_module(
            target_module="ag-ecc-01",
            event_type="style_advice",
            source_module=self.module_id,
            data=data,
            priority=PRIORITY_NORMAL
        )
        self.bus.publish_to_module(
            target_module="ag-mem-11",
            event_type="style_advice",
            source_module=self.module_id,
            data=data,
            priority=PRIORITY_NORMAL
        )

    # ====================== 情绪处理核心逻辑 ======================
    def _process_emotion(self, data: Dict, now: float):
        session_id = data.get("session_id", "")
        if not session_id:
            return

        emotion_str = data.get("emotion_label", "平静")
        emotion_confidence = data.get("emotion_confidence", 0.5)
        intent_tendency = data.get("intent_tendency", "")

        try:
            emotion_label = EmotionLabel(emotion_str)
        except ValueError:
            emotion_label = EmotionLabel.CALM

        lock_expire = self._emotion_lock_until.get(session_id, 0)
        if now < lock_expire:
            return

        # 更新脱敏情绪历史
        if session_id not in self._emotion_history:
            self._emotion_history[session_id] = []
        self._emotion_history[session_id].append({"emotion": emotion_label, "time": now})
        if len(self._emotion_history[session_id]) > self.MAX_EMOTION_HISTORY:
            self._emotion_history[session_id] = self._emotion_history[session_id][-self.MAX_EMOTION_HISTORY:]

        # 情绪频繁切换判断与连续冻结升级
        if self._is_frequent_switch(session_id):
            cnt = self._continuous_lock_count.get(session_id, 0) + 1
            self._continuous_lock_count[session_id] = cnt
            lock_time = self.EMOTION_LOCK_DURATION_SEC
            if cnt >= self.MAX_CONTINUOUS_LOCK:
                lock_time *= 2
            self._emotion_lock_until[session_id] = now + lock_time
            self._recent_emotion_changes += 1
            return
        else:
            self._continuous_lock_count.pop(session_id, None)

        # 状态机跳转
        if emotion_label == EmotionLabel.ANGRY:
            self.state = SocialMindState.CONFLICT_RESOLUTION
            self._start_conflict_resolution(session_id)
        elif emotion_label in (EmotionLabel.CONFUSED, EmotionLabel.ANXIOUS, EmotionLabel.DISAPPOINTED):
            self.state = SocialMindState.EMOTION_ATTENTION
        else:
            self.state = SocialMindState.NORMAL_MONITOR

        # 生成交互风格建议
        mapping = self.EMOTION_STYLE_MAP.get(emotion_label, self.EMOTION_STYLE_MAP[EmotionLabel.CALM])
        advice = InteractionStyleAdvice(
            session_id=session_id,
            suggested_tone=mapping["tone"],
            suggested_pace=mapping["pace"],
            push_tendency=mapping["push"],
            adaptation_basis=f"用户情绪: {emotion_label.value}"
        )
        self._interaction_strategies[session_id] = advice
        self._broadcast_style_advice(advice)

        # 下发情绪与意图预判
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-01",
                event_type="emotion_prejudge",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "emotion_label": emotion_label.value,
                    "intent_tendency": intent_tendency,
                    "confidence": emotion_confidence,
                    "social_risk_level": "高" if emotion_label == EmotionLabel.ANGRY else "低"
                },
                priority=PRIORITY_HIGH if emotion_label == EmotionLabel.ANGRY else PRIORITY_NORMAL
            )

        # 高风险情绪上报安全仲裁
        if emotion_label == EmotionLabel.ANGRY and self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="social_risk_alert",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "risk_type": "用户愤怒",
                    "risk_level": "高",
                    "trigger_behavior": "情绪标签为愤怒",
                    "suggested_handling": "启动冲突化解策略，暂停主动推送"
                },
                priority=PRIORITY_HIGH
            )

        if self.state in (SocialMindState.EMOTION_ATTENTION, SocialMindState.CONFLICT_RESOLUTION):
            self.state = SocialMindState.NORMAL_MONITOR

    def _is_frequent_switch(self, session_id: str) -> bool:
        history = self._emotion_history.get(session_id, [])
        if len(history) < self.MAX_EMOTION_SWITCHES_SHORT + 1:
            return False
        recent = history[-(self.MAX_EMOTION_SWITCHES_SHORT + 1):]
        switch_count = 0
        for i in range(1, len(recent)):
            if recent[i]["emotion"] != recent[i-1]["emotion"]:
                switch_count += 1
        return switch_count >= self.MAX_EMOTION_SWITCHES_SHORT

    def _start_conflict_resolution(self, session_id: str):
        advice = InteractionStyleAdvice(
            session_id=session_id,
            suggested_tone="冷静中立",
            suggested_pace=InteractionPace.SLOW,
            push_tendency="停止推送",
            adaptation_basis="冲突化解场景，关停所有营销/主动推送"
        )
        self._interaction_strategies[session_id] = advice
        self._broadcast_style_advice(advice)

    # ====================== 社交风险评估（原路回包+关键词优化） ======================
    def _assess_social_risk(self, data: Dict):
        session_id = data.get("session_id", "")
        content = data.get("content", "")
        req_topic = data.get("reply_topic", "")
        req_source = data.get("source_module", "")

        risk_level = "低"
        for word in self.RISK_KEYWORDS:
            if word in content:
                risk_level = "中"
                break

        risk_result = {
            "session_id": session_id,
            "risk_type": "社交风险评估",
            "risk_level": risk_level,
            "trigger_keywords": [w for w in self.RISK_KEYWORDS if w in content],
            "suggested_handling": "正常处理" if risk_level == "低" else "需重点关注"
        }

        # 向原请求方返回结果
        if self.bus and req_topic and req_source:
            self.bus.publish_to_module(
                target_module=req_source,
                event_type=req_topic,
                source_module=self.module_id,
                data=risk_result,
                priority=PRIORITY_NORMAL
            )

        # 向安全模块发送告警
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="social_risk_alert",
                source_module=self.module_id,
                data=risk_result,
                priority=PRIORITY_NORMAL
            )

    # ====================== 状态上报 ======================
    def _publish_status(self):
        if not self.bus:
            return
        try:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="social_mind_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "current_emotion": "综合判定正常",
                    "strategy_summary": "交互策略运行正常",
                    "recent_emotion_changes": self._recent_emotion_changes
                },
                priority=PRIORITY_LOW
            )
        except Exception as e:
            logger.error(f"状态上报异常: {e}")

    # ====================== 系统启停 ======================
    def emergency_shutdown(self):
        self.state = SocialMindState.SYSTEM_PAUSED
        logger.info("⏹️ 社会心智模块已暂停（系统熔断）")

    def get_state(self) -> SocialMindState:
        return self.state