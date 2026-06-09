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
  - 对接三总线架构（InternalBus + MemoryBus + CerebellumBus）
  - 严格实施 ag-ecc-12 作为唯一对外网关的安全边界
  - 提供端到端演示场景

修改记录：
  - V1.0: 修正主循环方法名对齐 CPEC 标准，实现双总线安全架构
  - V1.0: 移除越权的对端模块注册，保持主入口简洁
  - V1.0: 恢复 CerebellumBus 并注册对端模块，对齐架构白皮书
"""

import time
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 三总线导入（CerebellumBus 复用 MemoryBus 接口，物理隔离实例）
from memory_bus import InternalBus, MemoryBus
CerebellumBus = MemoryBus

# 导入模块注册表（仅用于校验）
from module_registry import MODULE_REGISTRY

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
    ECC 认知大脑 主控类 V1.0
    负责模块实例化、主循环调度、三总线安全架构
    """

    ECC_MODULE_ID_PATTERN = re.compile(r"^ag-ecc-\d{2}$")

    def __init__(self):
        self.cycle_count = 0
        self.running = True

        # ====================== 三总线架构（架构白皮书强制） ======================
        self.internal_bus = InternalBus(validate_modules=False)      # ECC 内部通信
        self.external_bus = MemoryBus(validate_modules=False)        # ECC ↔ MLNF（记忆）
        self.cerebellum_bus = CerebellumBus(validate_modules=False)  # ECC ↔ MCC（工具调用）

        # 模块ID → 实例映射
        self.module_map = {}

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

        # 绑定模块ID、校验注册表、注入总线、注册模块、绑定回调
        self._bind_module_ids()
        self._validate_registry()
        self._inject_bus()
        self._register_modules()
        self._wire_callbacks()

        print("Agent-ecc-brain 认知大脑 初始化完成")
        print(f"  模块总数: {len(self.module_map)} (注册表校验通过)")

    def _bind_module_ids(self):
        """绑定ECC标准模块ID（CPEC V1.0 强制）"""
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

    def _validate_registry(self):
        """注册表兼容性校验"""
        if len(self.module_map) != 12:
            raise RuntimeError(
                f"ECC 模块数量异常: 期望 12 个，实际 {len(self.module_map)} 个"
            )
        for mid in self.module_map:
            if not self.ECC_MODULE_ID_PATTERN.match(mid):
                raise RuntimeError(f"非法 ECC 模块 ID: {mid}")

    def _inject_bus(self):
        """
        注入三总线（严格遵循 ag-ecc-12 唯一对外网关原则）
        - 所有模块获得内部总线 InternalBus
        - 仅 ag-ecc-12 获得两条对外总线（MemoryBus + CerebellumBus）
        """
        for mid, module in self.module_map.items():
            module.bus = self.internal_bus
        # 仅网关拥有对外通信能力
        self.resource_scheduler.external_bus = self.external_bus
        self.resource_scheduler.cerebellum_bus = self.cerebellum_bus

    def _register_modules(self):
        """注册模块到总线（仅注册本系统模块 + 对端唯一入口）"""
        # 1. 内部总线注册所有 ECC 模块
        for mid in self.module_map.keys():
            self.internal_bus.register_module(mid)
        
        # 2. 外部总线注册本端网关 + 对端 MLNF 唯一入口
        self.external_bus.register_module("ag-ecc-12")
        self.external_bus.register_module("ag-mem-01")
        
        # 3. 小脑总线注册本端网关 + 对端 MCC 唯一入口
        self.cerebellum_bus.register_module("ag-ecc-12")
        self.cerebellum_bus.register_module("ag-mcc-01")

    def _wire_callbacks(self):
        """绑定模块消息回调"""
        for mid, module in self.module_map.items():
            if hasattr(module, "handle_message"):
                self.internal_bus.subscribe_to_module(mid, module.handle_message)
        # 仅网关监听两条对外总线
        if hasattr(self.resource_scheduler, "handle_message"):
            self.external_bus.subscribe_to_module(
                "ag-ecc-12", self.resource_scheduler.handle_message
            )
            self.cerebellum_bus.subscribe_to_module(
                "ag-ecc-12", self.resource_scheduler.handle_message
            )

    # ====================== 主循环 ======================
    def run_cycle(self):
        """
        执行一个主循环周期（严格对齐 CPEC V1.0）
        """
        # 1. 处理所有外部输入
        self.external_bus.process_batch(100)
        self.cerebellum_bus.process_batch(100)
        self.internal_bus.process_batch(100)

        # 2. 按依赖顺序调用各模块主逻辑
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

        # 3. 处理所有外部输出
        self.internal_bus.process_batch(100)
        self.cerebellum_bus.process_batch(100)
        self.external_bus.process_batch(100)

        self.cycle_count += 1

    def get_health_status(self):
        """健康监控"""
        return {
            "cycle_count": self.cycle_count,
            "running": self.running,
            "loaded_modules": len(self.module_map),
            "internal_pending": self.internal_bus.pending_count(),
            "external_pending": self.external_bus.pending_count(),
            "cerebellum_pending": self.cerebellum_bus.pending_count(),
        }

    def shutdown(self):
        """安全关闭"""
        self.running = False
        for mid in reversed(list(self.module_map.keys())):
            module = self.module_map[mid]
            try:
                if hasattr(module, "shutdown"):
                    module.shutdown()
            except Exception as e:
                print(f"  [WARN] 关闭模块 {mid} 异常: {e}")
        print("Agent-ecc-brain 已安全关闭")


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

    health = brain.get_health_status()
    print(f"\n✅ Agent-ecc-brain 演示完成")
    print(f"  总周期数: {health['cycle_count']}")
    print(f"  已加载模块: {health['loaded_modules']}/12")
    print(f"  内部待处理消息: {health['internal_pending']}")
    print(f"  记忆总线待处理: {health['external_pending']}")
    print(f"  小脑总线待处理: {health['cerebellum_pending']}")


if __name__ == "__main__":
    main()
