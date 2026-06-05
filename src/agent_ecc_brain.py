#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-ecc-brain 认知大脑 · 主入口
版本：V1.0
原创提出者：文波福
开源协议：CC BY-NC 4.0

职责：
  - 实例化全部 12 个 ECC 认知大脑模块
  - 实现主循环：逐模块调用 run_xxx_cycle()
  - 提供端到端演示场景

注意：
  如果模块文件名使用连字符（如 ag-ecc-01-intent-parser.py），
  Python 无法直接导入。请将文件名中的连字符替换为下划线，
  或将本文件中的导入语句改为 importlib 动态导入。
  当前版本假设模块文件名已使用下划线命名。
"""

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    """
    ECC 认知大脑 主控类
    负责模块实例化与主循环调度
    """

    def __init__(self):
        self.cycle_count = 0
        self.running = True

        # ========== 实例化全部 12 个模块 ==========
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

        print("Agent-ecc-brain 认知大脑 初始化完成")
        print(f"  模块总数: 12")

    def run_cycle(self):
        """执行一个主循环周期"""
        self.intent_parser.run_parse_cycle()
        self.task_planner.run_planning_cycle()
        self.tool_selector.run_selection_cycle()
        self.safety_arbiter.run_arbiter_cycle()
        self.memory_query.run_query_cycle()
        self.result_evaluator.run_evaluation_cycle()
        self.working_memory.run_memory_cycle()
        self.metacognition.run_metacognition_cycle()
        self.intrinsic_motivation.run_motivation_cycle()
        self.social_mind.run_social_cycle()
        self.abstract_creation.run_creation_cycle()
        self.resource_scheduler.run_scheduler_cycle()

        self.cycle_count += 1

    def shutdown(self):
        """安全关闭"""
        self.running = False
        print("Agent-ecc-brain 已关闭")


def main():
    print("=" * 70)
    print("  Agent-ecc-brain 认知大脑 V1.0")
    print("  原创提出者：文波福")
    print("=" * 70)

    brain = AgentEccBrain()

    print("\n运行 3 个主循环周期...")
    for i in range(3):
        brain.run_cycle()
        print(f"  周期 {i+1} 完成")

    print(f"\n✅ Agent-ecc-brain 演示完成, 总周期数: {brain.cycle_count}")


if __name__ == "__main__":
    main()