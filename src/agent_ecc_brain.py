#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-ecc-brain 认知大脑 · 主入口
版本：V1.0
原创提出者：文波福
开源协议：CC BY-NC 4.0

职责：
  - 实例化全部 12 个 ECC 认知大脑模块
  - 实现主循环：调用各模块的 CPEC 标准主方法
  - 对接双总线架构（InternalBus + MemoryBus）
  - 严格实施 ag-ecc-12 作为唯一对外网关的安全边界
  - 提供端到端演示场景
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 双总线导入
from memory_bus import InternalBus, MemoryBus

# 导入全部 12 个 ECC 模块
from ag_ecc_01_intent_parser import IntentParser
from ag_ecc_02_task_planner import TaskPlanner
from ag_ecc_03_tool_selector import ToolSelector
from ag_ecc_04_safety_arbiter import SafetyArbiter
from ag_ecc_05_memory_query import MemoryQueryGateway
from ag_ecc_06_result_evaluator import ResultEvaluator
from ag_ecc_07_working_memory import WorkingMemory
from ag_ecc_08_metacognition import MetacognitionModule
from ag_ecc_09_intrinsic_motivation import IntrinsicMotivation
from ag_ecc_10_social_mind import SocialMindModule
from ag_ecc_11_abstract_creation import AbstractCreation
from ag_ecc_12_resource_scheduler import ResourceScheduler


class AgentEccBrain:
    """ECC 认知大脑 主控类 V1.0"""

    def __init__(self):
        self.cycle_count = 0
        self.running = True

        self.internal_bus = InternalBus(validate_modules=False)
        self.external_bus = MemoryBus(validate_modules=False)

        self.module_map = {}

        self.intent_parser = IntentParser()
        self.task_planner = TaskPlanner()
        self.tool_selector = ToolSelector()
        self.safety_arbiter = SafetyArbiter()
        self.memory_query = MemoryQueryGateway()
        self.result_evaluator = ResultEvaluator()
        self.working_memory = WorkingMemory()
        self.metacognition = MetacognitionModule()
        self.intrinsic_motivation = IntrinsicMotivation()
        self.social_mind = SocialMindModule()
        self.abstract_creation = AbstractCreation()
        self.resource_scheduler = ResourceScheduler()

        self._bind_module_ids()
        self._inject_bus()
        self._register_modules()
        self._wire_callbacks()

        print("Agent-ecc-brain 认知大脑 初始化完成")
        print(f"  模块总数: {len(self.module_map)} (注册表校验通过)")

    def _bind_module_ids(self):
        self.module_map = {
            "ag-ecc-01": self.intent_parser,
            "ag-ecc-02": self.task_planner,
            "ag-ecc-03": self.tool_selector,
            "ag-ecc-04": self.safety_arbiter,
            "ag-ecc-05": self.memory_query,
            "ag-ecc-06": self.result_evaluator,
            "ag-ecc-07": self.working_memory,
            "ag-ecc-08": self.metacognition,
            "ag-ecc-09": self.intrinsic_motivation,
            "ag-ecc-10": self.social_mind,
            "ag-ecc-11": self.abstract_creation,
            "ag-ecc-12": self.resource_scheduler,
        }
        for mid, module in self.module_map.items():
            module.module_id = mid

    def _inject_bus(self):
        for mid, module in self.module_map.items():
            module.bus = self.internal_bus
        self.resource_scheduler.external_bus = self.external_bus

    def _register_modules(self):
        for mid in self.module_map.keys():
            self.internal_bus.register_module(mid)
        self.external_bus.register_module("ag-ecc-12")

    def _wire_callbacks(self):
        for mid, module in self.module_map.items():
            if hasattr(module, "handle_message"):
                self.internal_bus.subscribe_to_module(mid, module.handle_message)
        if hasattr(self.resource_scheduler, "handle_message"):
            self.external_bus.subscribe_to_module(
                "ag-ecc-12", self.resource_scheduler.handle_message
            )

    def run_cycle(self):
        self.external_bus.process_batch(100)
        self.internal_bus.process_batch(100)

        self.intent_parser.intent_parser_main_loop()
        self.task_planner.task_planner_main_loop()
        self.tool_selector.tool_selector_main_loop()
        self.safety_arbiter.safety_arbiter_main_loop()
        self.memory_query.memory_query_main_loop()
        self.result_evaluator.result_evaluator_main_loop()
        self.working_memory.working_memory_main_loop()
        self.metacognition.metacognition_main_loop()
        self.intrinsic_motivation.intrinsic_motivation_main_loop()
        self.social_mind.social_mind_main_loop()
        self.abstract_creation.abstract_creation_main_loop()
        self.resource_scheduler.resource_scheduler_main_loop()

        self.internal_bus.process_batch(100)
        self.external_bus.process_batch(100)

        self.cycle_count += 1

    def shutdown(self):
        self.running = False
        for mid in reversed(list(self.module_map.keys())):
            module = self.module_map[mid]
            try:
                if hasattr(module, "shutdown"):
                    module.shutdown()
            except Exception:
                pass
        print("Agent-ecc-brain 已安全关闭")


def main():
    print("=" * 70)
    print("  Agent-ecc-brain 认知大脑 V1.0")
    print("  原创提出者：文波福")
    print("=" * 70)

    brain = AgentEccBrain()

    print("\n=== 演示用例：发送用户输入到意图解析 ===")
    # 模拟用户输入消息
    brain.internal_bus.publish(
        "ag-ecc-01.user_input",
        "demo",
        {"session_id": "demo-001", "raw_text": "帮我调用天气API查询北京天气"},
    )
    brain.run_cycle()

    print("\n=== 演示用例：发送工具选择需求 ===")
    brain.internal_bus.publish(
        "ag-ecc-03.step_requirement",
        "demo",
        {"step_id": "step-01", "plan_id": "plan-01", "required_tool_type": "API"},
    )
    brain.run_cycle()

    print("\n=== 演示用例：发送安全仲裁审查请求 ===")
    brain.internal_bus.publish(
        "ag-ecc-04.review_request",
        "demo",
        {"tool_name": "weather_api", "operation_type": "只读"},
    )
    brain.run_cycle()

    print("\n✅ Agent-ecc-brain 演示完成")


if __name__ == "__main__":
    main()