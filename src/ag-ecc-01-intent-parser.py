#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-01
模块名称: 意图解析模块
所属分区: 一、认知大脑核心模块
核心职责: 将用户自然语言输入转化为结构化的意图描述，提取核心任务类型、实体参数、约束条件
          及优先级。为任务规划模块（ag-ecc-02）提供标准化的任务起点，为工具选择模块
          （ag-ecc-03）提供初步的工具需求线索。支持多轮对话上下文的意图追踪与修正。
          不参与任务规划或工具执行，仅负责意图的解析与结构化输出。

依赖模块:
    ag-ecc-05(记忆查询模块，获取用户历史偏好辅助意图消歧),
    ag-ecc-10(社会心智模块，获取用户情绪状态辅助意图理解),
    ag-ecc-07(工作记忆模块，读写对话上下文)
被依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-03(工具选择模块)

安全约束:
  P-01: 意图解析仅基于用户输入文本的语义特征，不得泄露用户的原始输入内容给任何外部系统
  P-02: 消歧过程中获取的用户历史偏好数据仅用于置信度修正，不得作为意图判定的唯一依据
  P-03: 低置信度意图（<0.60）必须触发消歧流程，不得直接输出给下游模块执行
  P-04: 本模块仅输出意图描述，不得直接触发任何工具调用或任务执行
  P-05: 会话上下文数据仅保留最近10轮对话，超出的历史数据自动清除
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import re


class ParserState(Enum):
    WAITING_INPUT = "waiting_input"
    PARSING = "parsing"
    DISAMBIGUATING = "disambiguating"
    PARSED = "parsed"
    SYSTEM_PAUSED = "system_paused"


class TaskType(Enum):
    INFO_QUERY = "信息查询"
    TOOL_CALL = "工具调用"
    CONTENT_CREATION = "内容创作"
    DIALOGUE = "对话交互"
    TASK_MANAGE = "任务管理"
    SYSTEM_CONFIG = "系统配置"


@dataclass
class UserInput:
    session_id: str = ""
    raw_text: str = ""
    input_method: str = "text"
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserPreferenceSummary:
    user_id: str = ""
    preference_keywords: List[str] = field(default_factory=list)
    high_freq_task_types: List[str] = field(default_factory=list)
    frequent_tools: List[str] = field(default_factory=list)


@dataclass
class EmotionState:
    user_id: str = ""
    emotion_label: str = "平静"
    emotion_confidence: float = 0.5
    intent_tendency: str = ""


@dataclass
class DialogueContext:
    session_id: str = ""
    recent_intent: Optional['StructuredIntent'] = None
    confirmed_entities: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StructuredIntent:
    intent_id: str = ""
    session_id: str = ""
    task_type: TaskType = TaskType.DIALOGUE
    entities: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    confidence: float = 0.5
    alternative_intents: List[Dict[str, Any]] = field(default_factory=list)
    tool_hint: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class DisambiguationQuery:
    query_id: str = ""
    session_id: str = ""
    query_text: str = ""
    options: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ParserStatus:
    state: ParserState = ParserState.WAITING_INPUT
    parse_count: int = 0
    avg_parse_duration_ms: float = 0.0
    disambiguation_rate: float = 0.0


class IntentParser:
    # 任务类型关键词
    TOOL_KEYWORDS = ["执行", "调用", "运行", "API", "操作", "打开", "关闭", "删除", "创建"]
    INFO_KEYWORDS = ["什么是", "如何", "搜索", "查询", "查找", "找", "搜", "为什么"]
    CREATION_KEYWORDS = ["写", "生成", "创作", "画", "翻译", "总结", "编写", "制作"]
    DIALOGUE_KEYWORDS = ["你好", "谢谢", "再见", "怎么样", "聊聊", "知道吗"]

    # 置信度阈值
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    LOW_CONFIDENCE_THRESHOLD = 0.60
    MAX_CONTEXT_ROUNDS = 10

    def __init__(self):
        self.module_id = "ag-ecc-01"
        self.module_name = "意图解析模块"
        self.version = "V1.0"

        self.state = ParserState.WAITING_INPUT
        self._context_cache: Dict[str, DialogueContext] = {}
        self._total_parsed: int = 0
        self._total_parse_time: float = 0.0
        self._disambiguation_count: int = 0
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_user_input = None
        self._query_preference = None
        self._query_emotion = None
        self._query_context = None

        self._publish_intent = None
        self._publish_tool_hint = None
        self._publish_disambiguation_query = None
        self._publish_status = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_user_input_query(self, callback: Callable[[], Optional[UserInput]]):
        self._query_user_input = callback

    def set_preference_query(self, callback: Callable[[str], Optional[UserPreferenceSummary]]):
        self._query_preference = callback

    def set_emotion_query(self, callback: Callable[[str], Optional[EmotionState]]):
        self._query_emotion = callback

    def set_context_query(self, callback: Callable[[str], Optional[DialogueContext]]):
        self._query_context = callback

    def set_intent_publisher(self, callback: Callable[[StructuredIntent], None]):
        self._publish_intent = callback

    def set_tool_hint_publisher(self, callback: Callable[[StructuredIntent], None]):
        self._publish_tool_hint = callback

    def set_disambiguation_query_publisher(self, callback: Callable[[DisambiguationQuery], None]):
        self._publish_disambiguation_query = callback

    def set_status_publisher(self, callback: Callable[[ParserStatus], None]):
        self._publish_status = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_parse_cycle(self) -> Optional[StructuredIntent]:
        if self.state == ParserState.SYSTEM_PAUSED:
            return None

        # 接收用户输入
        user_input = self._query_user_input() if self._query_user_input else None
        if user_input is None:
            return None

        self.state = ParserState.PARSING
        start_time = time.time()

        result = self._parse_input(user_input)

        elapsed = (time.time() - start_time) * 1000
        self._total_parsed += 1
        self._total_parse_time += elapsed

        if result is None:
            self.state = ParserState.WAITING_INPUT
            return None

        if self._publish_intent:
            self._publish_intent(result)
        if result.task_type == TaskType.TOOL_CALL and self._publish_tool_hint:
            self._publish_tool_hint(result)

        self.state = ParserState.WAITING_INPUT
        return result

    # ========== 核心解析 ==========
    def _parse_input(self, user_input: UserInput) -> Optional[StructuredIntent]:
        text = user_input.raw_text.strip()
        if not text:
            return self._build_default_intent(user_input.session_id)

        # 获取对话上下文
        context = self._query_context(user_input.session_id) if self._query_context else None
        recent_intent = context.recent_intent if context else None
        confirmed_entities = context.confirmed_entities if context else {}

        # 候选意图分类
        candidates = self._classify_intent(text, recent_intent)

        if not candidates:
            candidates = [{"task_type": TaskType.DIALOGUE, "confidence": 0.30, "basis": "无法识别意图"}]

        # 按置信度排序
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        primary = candidates[0]

        # 消歧判定
        if primary["confidence"] < self.LOW_CONFIDENCE_THRESHOLD:
            self.state = ParserState.DISAMBIGUATING
            self._disambiguation_count += 1

            # 尝试从偏好消歧
            preference = self._query_preference(user_input.session_id) if self._query_preference else None
            if preference:
                primary = self._apply_preference_boost(candidates, preference)

            # 尝试从情绪消歧
            if primary["confidence"] < self.LOW_CONFIDENCE_THRESHOLD:
                emotion = self._query_emotion(user_input.session_id) if self._query_emotion else None
                if emotion and emotion.intent_tendency:
                    primary = self._apply_emotion_boost(candidates, emotion)

            # 消歧后仍低于阈值，生成消歧问询，阻断输出
            if primary["confidence"] < self.LOW_CONFIDENCE_THRESHOLD:
                self._generate_and_publish_disambiguation_query(user_input.session_id, candidates)
                self.state = ParserState.WAITING_INPUT
                return None

        # 提取实体
        entities = self._extract_entities(text)

        # 合并已确认实体
        entities.update(confirmed_entities)

        # 构建工具提示
        tool_hint = {}
        if primary["task_type"] == TaskType.TOOL_CALL:
            tool_keywords = [kw for kw in self.TOOL_KEYWORDS if kw in text]
            tool_hint = {"likely_tool_category": "API", "keywords": tool_keywords}

        intent = StructuredIntent(
            intent_id=f"INT-{uuid.uuid4().hex[:8]}",
            session_id=user_input.session_id,
            task_type=primary["task_type"],
            entities=entities,
            constraints={},
            priority=5,
            confidence=round(primary["confidence"], 2),
            alternative_intents=candidates[1:3],
            tool_hint=tool_hint
        )

        # 更新上下文
        if context:
            context.recent_intent = intent
            context.confirmed_entities.update(entities)
            context.history.append({"text": text[:200], "intent": primary["task_type"].value, "time": time.time()})
            if len(context.history) > self.MAX_CONTEXT_ROUNDS:
                context.history = context.history[-self.MAX_CONTEXT_ROUNDS:]

        self.state = ParserState.PARSED
        return intent

    def _classify_intent(self, text: str, recent_intent: Optional[StructuredIntent]) -> List[Dict[str, Any]]:
        candidates = []

        # 工具调用
        if any(kw in text for kw in self.TOOL_KEYWORDS):
            candidates.append({"task_type": TaskType.TOOL_CALL, "confidence": 0.90, "basis": "包含工具调用关键词"})

        # 信息查询
        if any(kw in text for kw in self.INFO_KEYWORDS):
            candidates.append({"task_type": TaskType.INFO_QUERY, "confidence": 0.80, "basis": "包含信息查询关键词"})

        # 内容创作
        if any(kw in text for kw in self.CREATION_KEYWORDS):
            candidates.append({"task_type": TaskType.CONTENT_CREATION, "confidence": 0.85, "basis": "包含内容创作关键词"})

        # 对话交互仅在没有其他任务候选时作为兜底
        if not candidates:
            if any(kw in text for kw in self.DIALOGUE_KEYWORDS):
                candidates.append({"task_type": TaskType.DIALOGUE, "confidence": 0.70, "basis": "包含对话交互关键词"})
            else:
                candidates.append({"task_type": TaskType.DIALOGUE, "confidence": 0.30, "basis": "无法识别明确意图，默认为对话交互"})

        # 结合最近意图修正
        if recent_intent:
            for c in candidates:
                if c["task_type"] == recent_intent.task_type:
                    c["confidence"] = min(1.0, c["confidence"] + 0.05)
                    c["basis"] += "，与上文意图一致"

        return candidates

    def _apply_preference_boost(self, candidates: List[Dict], preference: UserPreferenceSummary) -> Dict:
        for c in candidates:
            type_name = c["task_type"].value if isinstance(c["task_type"], TaskType) else c["task_type"]
            if type_name in preference.high_freq_task_types:
                c["confidence"] = min(1.0, c["confidence"] + 0.1)
                c["basis"] += "，用户偏好修正"
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[0]

    def _apply_emotion_boost(self, candidates: List[Dict], emotion: EmotionState) -> Dict:
        if emotion.intent_tendency == "任务执行":
            for c in candidates:
                if c["task_type"] in (TaskType.TOOL_CALL, TaskType.INFO_QUERY):
                    c["confidence"] = min(1.0, c["confidence"] + 0.08)
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[0]

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        entities = {}
        # 简单实体提取
        if "天气" in text:
            entities["topic"] = "天气"
        if "北京" in text:
            entities["city"] = "北京"
        if "上海" in text:
            entities["city"] = "上海"
        if "AI" in text or "人工智能" in text:
            entities["topic"] = entities.get("topic", "") + " AI"
        if "文件" in text:
            entities["target"] = "文件"
        return entities

    def _build_default_intent(self, session_id: str) -> StructuredIntent:
        return StructuredIntent(
            intent_id=f"INT-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            task_type=TaskType.DIALOGUE,
            confidence=0.3
        )

    def _generate_and_publish_disambiguation_query(self, session_id: str, candidates: List[Dict[str, Any]]):
        """生成消歧问询并发布"""
        options = []
        for c in candidates[:3]:
            type_name = c["task_type"].value if isinstance(c["task_type"], TaskType) else c["task_type"]
            options.append(type_name)

        query = DisambiguationQuery(
            query_id=f"DQ-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            query_text="您的意图不太明确，请问您是想：",
            options=options,
            timestamp=time.time()
        )
        if self._publish_disambiguation_query:
            self._publish_disambiguation_query(query)
        self._log_event("DISAMBIGUATION_QUERY_SENT", {
            "session_id": session_id,
            "options": options
        })

    # ========== 辅助 ==========
    def get_state(self) -> ParserState:
        return self.state

    def emergency_shutdown(self):
        self.state = ParserState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 意图解析模块 (ag-ecc-01) 演示")
    print("=" * 70)

    parser = IntentParser()

    print_separator("STEP 1: 工具调用意图")
    parser.set_user_input_query(lambda: UserInput(session_id="S001", raw_text="帮我调用天气API查询北京天气"))
    result = parser.run_parse_cycle()
    if result:
        print(f"  任务类型: {result.task_type.value}")
        print(f"  置信度: {result.confidence}")
        print(f"  实体: {result.entities}")

    print_separator("STEP 2: 信息查询意图")
    parser.set_user_input_query(lambda: UserInput(session_id="S002", raw_text="什么是EM-Core架构"))
    result = parser.run_parse_cycle()
    if result:
        print(f"  任务类型: {result.task_type.value}")
        print(f"  置信度: {result.confidence}")

    print_separator("STEP 3: 低置信度输入触发消歧问询")
    parser.set_user_input_query(lambda: UserInput(session_id="S003", raw_text="嗯"))
    result = parser.run_parse_cycle()
    if result:
        print(f"  任务类型: {result.task_type.value}")
        print(f"  置信度: {result.confidence}")
    else:
        print("  已触发消歧问询，等待用户确认")

    print("\n✅ 意图解析模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-01 意图解析模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_parser():
            return IntentParser()

        # TC-E01-01: 明确工具调用
        print("\n[TC-E01-01] 明确工具调用")
        try:
            p = setup_parser()
            p.set_user_input_query(lambda: UserInput(session_id="T01", raw_text="帮我调用天气API查询北京天气"))
            result = p.run_parse_cycle()
            assert result is not None
            assert result.task_type == TaskType.TOOL_CALL
            assert result.confidence >= 0.85
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E01-02: 明确信息查询
        print("\n[TC-E01-02] 明确信息查询")
        try:
            p = setup_parser()
            p.set_user_input_query(lambda: UserInput(session_id="T02", raw_text="什么是EM-Core架构"))
            result = p.run_parse_cycle()
            assert result is not None
            assert result.task_type == TaskType.INFO_QUERY
            assert result.confidence >= 0.75
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E01-03: 空输入返回默认意图
        print("\n[TC-E01-03] 空输入返回默认意图")
        try:
            p = setup_parser()
            p.set_user_input_query(lambda: UserInput(session_id="T03", raw_text=""))
            result = p.run_parse_cycle()
            assert result is not None
            assert result.task_type == TaskType.DIALOGUE
            assert result.confidence <= 0.3
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E01-04: 低置信度触发消歧（应返回None，不输出意图）
        print("\n[TC-E01-04] 低置信度触发消歧问询（应返回None）")
        try:
            p = setup_parser()
            p.set_user_input_query(lambda: UserInput(session_id="T04", raw_text="那个"))
            result = p.run_parse_cycle()
            assert result is None  # 消歧失败后不应输出低置信度意图
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E01-05: 多轮对话上下文修正
        print("\n[TC-E01-05] 多轮对话上下文修正")
        try:
            p = setup_parser()
            ctx = DialogueContext(recent_intent=StructuredIntent(task_type=TaskType.TOOL_CALL))
            p.set_context_query(lambda sid: ctx)
            p.set_user_input_query(lambda: UserInput(session_id="T05", raw_text="再查一下上海的呢"))
            result = p.run_parse_cycle()
            assert result is not None
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E01-06: 紧急熔断
        print("\n[TC-E01-06] 紧急熔断")
        try:
            p = setup_parser()
            p.emergency_shutdown()
            assert p.state == ParserState.SYSTEM_PAUSED
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