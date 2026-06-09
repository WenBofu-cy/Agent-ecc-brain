#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-01
模块名称: 意图解析模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责:
  将用户自然语言输入转化为结构化的意图描述，提取核心任务类型、实体参数、约束条件
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

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import re
import logging

# 总线消息数据结构
from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_CRITICAL


# 配置日志（生产环境可通过配置文件调整级别）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ag-ecc-01")


# ==================== 状态与类型定义 ====================
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
class StructuredIntent:
    intent_id: str = ""
    session_id: str = ""
    task_type: TaskType = TaskType.DIALOGUE
    entities: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    confidence: float = 0.5
    alternative_intents: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """序列化方法，确保枚举转换为字符串"""
        return {
            "intent_id": self.intent_id,
            "session_id": self.session_id,
            "task_type": self.task_type.value,
            "entities": self.entities,
            "constraints": self.constraints,
            "priority": self.priority,
            "confidence": self.confidence,
            "alternative_intents": [
                {**c, "task_type": c["task_type"].value} 
                for c in self.alternative_intents 
                if isinstance(c["task_type"], TaskType)
            ],
            "timestamp": self.timestamp
        }


# 上下文快照（从 ag-ecc-07 获取）
@dataclass
class DialogueContext:
    session_id: str = ""
    recent_intent: Optional[StructuredIntent] = None
    confirmed_entities: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


# 消息工具类
def _make_request_topic(module: str, action: str) -> str:
    return f"{module}.{action}"


class IntentParser:
    """意图解析模块 V1.0"""

    # 关键词集合（CPEC 对齐）
    TOOL_KEYWORDS = ["执行", "调用", "运行", "API", "操作", "打开", "关闭", "删除", "创建"]
    INFO_KEYWORDS = ["什么是", "如何", "搜索", "查询", "查找", "找", "搜", "为什么"]
    CREATION_KEYWORDS = ["写", "生成", "创作", "画", "翻译", "总结", "编写", "制作"]
    DIALOGUE_KEYWORDS = ["你好", "谢谢", "再见", "怎么样", "聊聊", "知道吗"]
    TASK_MANAGE_KEYWORDS = ["取消", "修改", "重试", "查看"]
    SYSTEM_CONFIG_KEYWORDS = ["设置", "配置", "开启", "关闭"]

    HIGH_CONFIDENCE_THRESHOLD = 0.85
    LOW_CONFIDENCE_THRESHOLD = 0.60
    MAX_CONTEXT_ROUNDS = 10

    def __init__(self):
        self.module_id = "ag-ecc-01"
        self.version = "V1.0"
        self.state = ParserState.WAITING_INPUT
        self.bus = None  # 由主入口注入 InternalBus
        self._pending_input: Optional[Dict[str, Any]] = None
        self._total_parsed: int = 0
        self._total_parse_time: float = 0.0
        self._disambiguation_count: int = 0
        self._last_status_report: float = 0.0  # 上次状态上报时间
        logger.info("意图解析模块初始化完成")

    def handle_message(self, msg: Message):
        """接收总线消息（点对点订阅模式）"""
        try:
            if msg.topic == _make_request_topic("ag-ecc-01", "user_input"):
                logger.info(f"收到用户输入，session_id: {msg.data.get('session_id')}")
                self._handle_user_input(msg.data)
            elif msg.topic == _make_request_topic("ag-ecc-01", "shutdown"):
                logger.info("收到关闭指令")
                self.emergency_shutdown()
            else:
                logger.warning(f"收到未知主题消息: {msg.topic}")
        except Exception as e:
            logger.error(f"处理消息异常: {str(e)}", exc_info=True)

    def _handle_user_input(self, data: Dict[str, Any]):
        """缓存用户输入数据，由主循环处理"""
        self._pending_input = data

    # ====================== 主循环（CPEC 对齐） ======================
    def intent_parser_main_loop(self):
        """主循环，CPEC 规定的方法名"""
        if self.state == ParserState.SYSTEM_PAUSED:
            return

        # 周期性状态上报
        self._try_status_report()

        # 检查是否有待处理的用户输入
        if self._pending_input is None:
            return

        input_data = self._pending_input
        self._pending_input = None
        session_id = input_data.get("session_id", "")

        try:
            self.state = ParserState.PARSING
            start_time = time.time()

            result = self._parse(input_data)

            elapsed = (time.time() - start_time) * 1000
            self._total_parsed += 1
            self._total_parse_time += elapsed

            if result is None:
                logger.info(f"解析完成，无有效意图输出，session_id: {session_id}")
                self.state = ParserState.WAITING_INPUT
                return

            # 标记解析完成状态
            self.state = ParserState.PARSED

            # 发布结构化意图到 ag-ecc-02
            self._publish_intent(result)

            # 若为工具调用，发布工具需求线索到 ag-ecc-03
            if result.task_type == TaskType.TOOL_CALL:
                self._publish_tool_hint(result)

            logger.info(f"解析成功，intent_id: {result.intent_id}, 耗时: {elapsed:.2f}ms, 置信度: {result.confidence}")

        except Exception as e:
            logger.error(f"解析主流程异常: {str(e)}", exc_info=True)
            self._send_parse_failed(session_id, "PARSE_ERROR", f"解析异常: {str(e)}")

        finally:
            self.state = ParserState.WAITING_INPUT

    def _parse(self, input_data: Dict[str, Any]) -> Optional[StructuredIntent]:
        session_id = input_data.get("session_id", "")
        raw_text = input_data.get("raw_text", "").strip()
        
        # 空输入统一进入消歧流程
        if not raw_text:
            logger.warning(f"收到空输入，session_id: {session_id}")
            self._send_disambiguation_query(session_id, [])
            return None

        # 获取对话上下文（通过总线同步请求）
        context = self._fetch_context(session_id)

        # 候选意图分类
        candidates = self._classify_intent(raw_text, context.recent_intent if context else None)

        # 消歧
        primary = self._disambiguate(candidates, session_id, raw_text)
        if primary is None:
            return None  # 消歧失败，不输出

        # 提取实体（从文本和已确认实体合并）
        entities = self._extract_entities(raw_text)
        if context and context.confirmed_entities:
            entities.update(context.confirmed_entities)

        intent = StructuredIntent(
            intent_id=f"INT-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            task_type=primary["task_type"],
            entities=entities,
            constraints={},
            priority=5,
            confidence=round(primary["confidence"], 2),
            alternative_intents=candidates[1:3]
        )

        # 更新上下文（发送回 ag-ecc-07）
        self._update_context(session_id, intent)

        return intent

    def _disambiguate(self, candidates: List[Dict[str, Any]], session_id: str, text: str) -> Optional[Dict[str, Any]]:
        if not candidates:
            self._send_disambiguation_query(session_id, [])
            return None

        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        primary = candidates[0]

        if primary["confidence"] >= self.LOW_CONFIDENCE_THRESHOLD:
            return primary

        # 低于 0.60，尝试消歧
        self.state = ParserState.DISAMBIGUATING
        self._disambiguation_count += 1
        logger.info(f"触发消歧流程，session_id: {session_id}, 最高置信度: {primary['confidence']}")

        # 1. 用户偏好
        pref = self._fetch_preference(session_id)
        if pref:
            primary = self._apply_preference_boost(candidates, pref)

        # 2. 情绪状态
        if primary["confidence"] < self.LOW_CONFIDENCE_THRESHOLD:
            emotion = self._fetch_emotion(session_id)
            if emotion:
                primary = self._apply_emotion_boost(candidates, emotion)

        # 若仍低于阈值，发送消歧问询并终止输出
        if primary["confidence"] < self.LOW_CONFIDENCE_THRESHOLD:
            self._send_disambiguation_query(session_id, candidates)
            return None

        return primary

    # ====================== 意图分类 ======================
    def _classify_intent(self, text: str, recent_intent: Optional[StructuredIntent]) -> List[Dict[str, Any]]:
        candidates = []

        if any(kw in text for kw in self.TASK_MANAGE_KEYWORDS):
            candidates.append({"task_type": TaskType.TASK_MANAGE, "confidence": 0.80, "basis": "包含任务管理关键词"})
        if any(kw in text for kw in self.SYSTEM_CONFIG_KEYWORDS):
            candidates.append({"task_type": TaskType.SYSTEM_CONFIG, "confidence": 0.80, "basis": "包含系统配置关键词"})
        if any(kw in text for kw in self.TOOL_KEYWORDS):
            candidates.append({"task_type": TaskType.TOOL_CALL, "confidence": 0.90, "basis": "包含工具调用关键词"})
        if any(kw in text for kw in self.INFO_KEYWORDS):
            candidates.append({"task_type": TaskType.INFO_QUERY, "confidence": 0.80, "basis": "包含信息查询关键词"})
        if any(kw in text for kw in self.CREATION_KEYWORDS):
            candidates.append({"task_type": TaskType.CONTENT_CREATION, "confidence": 0.85, "basis": "包含内容创作关键词"})
        if not candidates:
            if any(kw in text for kw in self.DIALOGUE_KEYWORDS):
                candidates.append({"task_type": TaskType.DIALOGUE, "confidence": 0.70, "basis": "对话交互关键词"})
            else:
                candidates.append({"task_type": TaskType.DIALOGUE, "confidence": 0.30, "basis": "无法识别意图"})

        if recent_intent:
            for c in candidates:
                if c["task_type"] == recent_intent.task_type:
                    c["confidence"] = min(1.0, c["confidence"] + 0.05)
                    c["basis"] += "，与上文意图一致"

        return candidates

    def _apply_preference_boost(self, candidates, pref):
        for c in candidates:
            if c["task_type"] in pref.get("high_freq_task_types", []):
                c["confidence"] = min(1.0, c["confidence"] + 0.1)
                c["basis"] += "，用户偏好修正"
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[0]

    def _apply_emotion_boost(self, candidates, emotion):
        if emotion.get("intent_tendency") == "任务执行":
            for c in candidates:
                if c["task_type"] in (TaskType.TOOL_CALL, TaskType.INFO_QUERY):
                    c["confidence"] = min(1.0, c["confidence"] + 0.08)
        candidates.sort(key=lambda x: x["confidence"], reverse=True)
        return candidates[0]

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        entities = {}
        city_pattern = re.findall(r"(北京|上海|广州|深圳|成都|杭州|武汉)", text)
        if city_pattern:
            entities["city"] = city_pattern[-1]

        time_pattern = re.findall(r"(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|今天|明天|后天)", text)
        if time_pattern:
            entities["date"] = time_pattern[0]

        if "天气" in text:
            entities["topic"] = "天气"
        if "文件" in text:
            entities["target"] = "文件"
        return entities

    # ====================== 总线通信 ======================
    def _fetch_context(self, session_id: str) -> Optional[DialogueContext]:
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic=_make_request_topic("ag-ecc-07", "query_context"),
                source_module=self.module_id,
                data={"session_id": session_id},
                target_module="ag-ecc-07",
                timeout_ms=500
            )
            if resp and resp.data:
                return DialogueContext(**resp.data)
            return None
        except (TypeError, ValueError, Exception) as e:
            logger.error(f"获取上下文异常: {str(e)}")
            return None

    def _fetch_preference(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic=_make_request_topic("ag-ecc-05", "query_preference"),
                source_module=self.module_id,
                data={"session_id": session_id},
                target_module="ag-ecc-05",
                timeout_ms=500
            )
            return resp.data if resp else None
        except Exception as e:
            logger.error(f"获取用户偏好异常: {str(e)}")
            return None

    def _fetch_emotion(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.bus:
            return None
        try:
            resp = self.bus.request(
                topic=_make_request_topic("ag-ecc-10", "query_emotion"),
                source_module=self.module_id,
                data={"session_id": session_id},
                target_module="ag-ecc-10",
                timeout_ms=500
            )
            return resp.data if resp else None
        except Exception as e:
            logger.error(f"获取用户情绪异常: {str(e)}")
            return None

    def _publish_intent(self, intent: StructuredIntent):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="intent_parsed",
                source_module=self.module_id,
                data=intent.to_dict(),
                priority=PRIORITY_HIGH
            )

    def _publish_tool_hint(self, intent: StructuredIntent):
        if self.bus:
            hint = {
                "intent_id": intent.intent_id,
                "task_type": intent.task_type.value,
                "entities": intent.entities,
                "suggested_tool_category": "API",
                "required_tool_features": [],
                "prefilled_params": {}
            }
            self.bus.publish_to_module(
                target_module="ag-ecc-03",
                event_type="tool_hint",
                source_module=self.module_id,
                data=hint,
                priority=PRIORITY_NORMAL
            )

    def _send_disambiguation_query(self, session_id: str, candidates: List[Dict[str, Any]]):
        options = []
        for c in candidates[:3]:
            type_name = c["task_type"].value if isinstance(c["task_type"], TaskType) else c["task_type"]
            options.append(type_name)
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="user_query",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "query_text": "您的意图不太明确，请问您是想：" if options else "我没有理解您的意思，请您再说清楚一些好吗？",
                    "options": options
                },
                priority=PRIORITY_HIGH
            )

    def _send_parse_failed(self, session_id: str, error_code: str, error_msg: str):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="parse_failed",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "error_code": error_code,
                    "error_msg": error_msg
                },
                priority=PRIORITY_NORMAL
            )

    def _update_context(self, session_id: str, intent: StructuredIntent):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-07",
                event_type="update_context",
                source_module=self.module_id,
                data={
                    "session_id": session_id,
                    "intent": intent.to_dict()
                },
                priority=PRIORITY_NORMAL
            )

    def _try_status_report(self):
        """周期性状态上报（每 60 秒向 ag-ecc-12 发送一次）"""
        if time.time() - self._last_status_report >= 60.0:
            if self.bus:
                self.bus.publish_to_module(
                    target_module="ag-ecc-12",
                    event_type="status_report",
                    source_module=self.module_id,
                    data={
                        "state": self.state.value,
                        "total_parsed": self._total_parsed,
                        "avg_parse_time_ms": self._total_parse_time / max(self._total_parsed, 1),
                        "disambiguation_rate": self._disambiguation_count / max(self._total_parsed, 1),
                    },
                    priority=PRIORITY_NORMAL
                )
            self._last_status_report = time.time()

    def emergency_shutdown(self):
        self.state = ParserState.SYSTEM_PAUSED
        logger.info("意图解析模块已暂停")

    def get_state(self) -> ParserState:
        return self.state

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_parsed": self._total_parsed,
            "avg_parse_time_ms": self._total_parse_time / self._total_parsed if self._total_parsed > 0 else 0,
            "disambiguation_count": self._disambiguation_count,
            "current_state": self.state.value
        }