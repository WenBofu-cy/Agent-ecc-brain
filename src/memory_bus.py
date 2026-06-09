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
  - V1.0: 修正注册表校验逻辑，适配 ECC 模块 ID 格式；增强关闭日志；显式注册对端模块
  - V1.0: 修复直接访问总线私有属性 _registered_modules，改用 is_module_registered()
  - V1.0: 分离 MemoryBus 与 CerebellumBus 的回调函数，消除路由歧义
"""

import time
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 三总线导入
from memory_bus import InternalBus, MemoryBus

# CerebellumBus 复用 MemoryBus 实现（规格要求的对外工具调用总线）
CerebellumBus = MemoryBus  # 接口完全兼容，物理隔离实例

# 导入模块注册表（用于校验，仅作参考）
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

    # 允许的 ECC 模块 ID 格式
    ECC_MODULE_ID_PATTERN = re.compile(r"^ag-ecc-\d{2}$")

    def __init__(self):
        self.cycle_count = 0
        self.running = True

        # ====================== 三总线架构 ======================
        self.internal_bus = InternalBus(validate_modules=False)      # 模块间内部通信
        self.external_bus = MemoryBus(validate_modules=False)        # 对外 MemoryBus（连接 MLNF）
        self.cerebellum_bus = CerebellumBus(validate_modules=False)  # 对外工具调用总线（连接 MCC）

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

        # 绑定模块ID、注入总线、注册模块、绑定回调
        self._bind_module_ids()
        self._validate_registry()   # 兼容注册表校验
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
        """
        注册表兼容性校验（V1.0 增强）
        - ECC 模块 ID 格式检查
        - 数量检查
        - 若模块 ID 存在于 MEM 注册表中，则不做冲突检查；仅检查自身一致性。
        """
        # 1. 模块数量检查
        if len(self.module_map) != 12:
            raise RuntimeError(
                f"ECC 模块数量异常: 期望 12 个，实际 {len(self.module_map)} 个"
            )

        # 2. ID 格式检查
        for mid in self.module_map:
            if not self.ECC_MODULE_ID_PATTERN.match(mid):
                raise RuntimeError(f"非法 ECC 模块 ID: {mid}")

        # 3. 若注册表中已包含 ECC 模块，则做双向校验；否则只做格式/数量检查
        ecc_in_registry = [mid for mid in self.module_map if mid in MODULE_REGISTRY]
        if ecc_in_registry:
            # 部分校验：已注册的 ECC 模块必须名称一致（可选）
            for mid in ecc_in_registry:
                expected_name = MODULE_REGISTRY[mid][0]  # 元组第一项是中文名称
                print(f"  注意: ECC 模块 {mid} 已存在于记忆中枢注册表 ({expected_name})")

        # 4. 确保所有需要通信的对端模块在外部总线上注册
        # 使用公共方法 is_module_registered 检查，避免访问私有属性
        if not self.external_bus.is_module_registered("ag-mem-01"):
            self.external_bus.register_module("ag-mem-01")

    def _inject_bus(self):
        """
        注入三总线（严格遵循 ag-ecc-12 唯一对外网关原则）
        - 所有模块获得内部总线 InternalBus
        - 仅 ag-ecc-12 获得外部总线 MemoryBus 和 CerebellumBus
        """
        for mid, module in self.module_map.items():
            module.bus = self.internal_bus

        # 只有资源调度模块拥有对外通信能力（MemoryBus + CerebellumBus）
        self.resource_scheduler.external_bus = self.external_bus
        self.resource_scheduler.cerebellum_bus = self.cerebellum_bus

    def _register_modules(self):
        """注册模块到总线（内部总线所有模块，外部总线仅 ag-ecc-12）"""
        for mid in self.module_map.keys():
            self.internal_bus.register_module(mid)
        # 外部总线仅注册网关模块
        self.external_bus.register_module("ag-ecc-12")
        self.cerebellum_bus.register_module("ag-ecc-12")

    def _wire_callbacks(self):
        """绑定模块消息回调，为不同总线使用不同的处理函数（消除路由歧义）"""
        # 内部总线统一用 handle_message
        for mid, module in self.module_map.items():
            if hasattr(module, "handle_message"):
                self.internal_bus.subscribe_to_module(mid, module.handle_message)

        # 外部总线分离：MemoryBus 和 CerebellumBus 使用独立的回调
        # 要求 ag-ecc-12 实现 handle_memory_bus_message 和 handle_cerebellum_bus_message
        if hasattr(self.resource_scheduler, "handle_memory_bus_message"):
            self.external_bus.subscribe_to_module(
                "ag-ecc-12", self.resource_scheduler.handle_memory_bus_message
            )
        if hasattr(self.resource_scheduler, "handle_cerebellum_bus_message"):
            self.cerebellum_bus.subscribe_to_module(
                "ag-ecc-12", self.resource_scheduler.handle_cerebellum_bus_message
            )

    # ====================== 主循环 ======================
    def run_cycle(self):
        """
        执行一个主循环周期（严格对齐 CPEC V1.0）
        各模块的主方法名为 CPEC 规定的标准名称
        """
        # 1. 处理外部输入（来自 MLNF-Mem、MCC、用户交互等）
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

        # 3. 收尾处理（发送响应、广播状态等）
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
        """安全关闭，逆序调用模块 shutdown 并记录异常"""
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
    print(f"  外部待处理消息: {health['external_pending']}")
    print(f"  小脑待处理消息: {health['cerebellum_pending']}")


if __name__ == "__main__":
    main()