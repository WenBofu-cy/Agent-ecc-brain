#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-ecc-brain 模块注册表
认知大脑 · AI Agent 专项实现

版本：V1.0
原创提出者：文波福
开源协议：CC BY-NC 4.0

模块编号采用 ag-ecc-01 至 ag-ecc-12，连续无断号。
每个条目包含：模块编号、中文名称、所属分区、核心职责摘要。
与 Agent-mlnf-mem 的 module_registry 风格完全统一。
"""

from typing import Dict, Optional, List, Tuple

MODULE_REGISTRY: Dict[str, Tuple[str, str, str]] = {
    # ========================
    # 认知大脑核心模块（ag-ecc-01 至 ag-ecc-12）
    # ========================
    "ag-ecc-01": (
        "意图解析模块",
        "一、认知大脑核心模块",
        "将用户自然语言输入转化为结构化意图、实体与任务类型，输出标准意图描述"
    ),
    "ag-ecc-02": (
        "任务规划模块",
        "一、认知大脑核心模块",
        "拆解复杂任务为可执行步骤序列，管理任务依赖与优先级排序"
    ),
    "ag-ecc-03": (
        "工具选择模块",
        "一、认知大脑核心模块",
        "根据任务需求与工具注册表匹配最合适的工具，评估工具调用代价与成功率"
    ),
    "ag-ecc-04": (
        "安全仲裁模块",
        "一、认知大脑核心模块",
        "全域安全最高管控单元，审查工具调用方案，执行工具白名单、权限检查与敏感操作确认"
    ),
    "ag-ecc-05": (
        "记忆查询模块",
        "一、认知大脑核心模块",
        "向双漏斗记忆中枢发起用户偏好查询与历史任务经验检索"
    ),
    "ag-ecc-06": (
        "结果评估模块",
        "一、认知大脑核心模块",
        "评估工具执行结果质量，判定任务完成度，触发记忆写入与经验更新"
    ),
    "ag-ecc-07": (
        "工作记忆模块",
        "一、认知大脑核心模块",
        "缓存当前会话的推理中间数据、任务状态与上下文，会话结束后自动清空"
    ),
    "ag-ecc-08": (
        "元认知模块",
        "一、认知大脑核心模块",
        "自我能力评估、置信度计算、未知意图识别，触发向用户或大模型求助"
    ),
    "ag-ecc-09": (
        "内生动机模块",
        "一、认知大脑核心模块",
        "基于用户习惯与未完成任务，主动生成建议、提醒或后续行动"
    ),
    "ag-ecc-10": (
        "社会心智模块",
        "一、认知大脑核心模块",
        "感知用户情绪状态与交互风格，适配回复语气与交互节奏"
    ),
    "ag-ecc-11": (
        "抽象创造模块",
        "一、认知大脑核心模块",
        "从任务经验中提炼通用规则，生成新的工具组合或策略（高阶，需授权激活）"
    ),
    "ag-ecc-12": (
        "资源调度模块",
        "一、认知大脑核心模块",
        "全局唯一对外网关，统筹工具调用权限、LLM API配额、系统资源分配与安全审计"
    ),
}


def get_module_info(module_id: str) -> Optional[Tuple[str, str, str]]:
    return MODULE_REGISTRY.get(module_id)

def list_all_modules() -> List[str]:
    return sorted(MODULE_REGISTRY.keys())

def get_module_count() -> int:
    return len(MODULE_REGISTRY)

def get_modules_by_zone(zone: str) -> Dict[str, Tuple[str, str, str]]:
    return {
        mid: info for mid, info in MODULE_REGISTRY.items()
        if zone in info[1]
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Agent-ecc-brain 模块注册表 单元测试")
    print("=" * 60)
    passed, failed = 0, 0

    print("\n[TC-REG-01] 注册表应包含12个模块")
    try:
        assert get_module_count() == 12
        print("   ✅ PASS")
        passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        failed += 1

    print("\n[TC-REG-02] 查询ag-ecc-01模块信息")
    try:
        info = get_module_info("ag-ecc-01")
        assert info is not None
        name, zone, role = info
        assert "意图解析" in name
        assert "认知大脑核心模块" in zone
        print("   ✅ PASS")
        passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        failed += 1

    print("\n[TC-REG-03] 编号ag-ecc-01至ag-ecc-12连续")
    try:
        all_ids = list_all_modules()
        expected = [f"ag-ecc-{i:02d}" for i in range(1, 13)]
        assert all_ids == expected
        print("   ✅ PASS")
        passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        failed += 1

    print("\n[TC-REG-04] 关键模块职责验证")
    try:
        _, _, role04 = get_module_info("ag-ecc-04")
        assert "安全" in role04 or "仲裁" in role04
        _, _, role12 = get_module_info("ag-ecc-12")
        assert "网关" in role12 or "调度" in role12
        print("   ✅ PASS")
        passed += 1
    except Exception as e:
        print(f"   ❌ FAIL: {e}")
        failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} PASS, {failed} FAIL")
    print("=" * 60)