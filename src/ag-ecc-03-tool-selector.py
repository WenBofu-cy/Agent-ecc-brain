#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-03
模块名称: 工具选择模块
所属分区: 一、认知大脑核心模块
核心职责: 接收 ag-ecc-02（任务规划模块）下发的步骤资源需求，在工具注册中心（ag-mcc-04）
          中检索匹配的工具清单，综合评估各工具的功能匹配度、调用成本、历史成功率与当前
          可用性，为每个步骤输出最优工具选择方案（含备选方案）。为 ag-ecc-02 提供工具能力
          约束信息以辅助任务规划。不参与工具的实际调用执行，仅负责工具的选择与推荐。

依赖模块:
    ag-ecc-02(任务规划模块), ag-ecc-05(记忆查询模块),
    ag-mcc-04(工具注册中心), ag-mcc-05(工具参数校验器)
被依赖模块:
    ag-ecc-02, ag-ecc-04(安全仲裁模块), ag-ecc-12(资源调度模块)

安全约束:
  S-01: 工具选择方案在下发执行前必须通过 ag-ecc-04 安全仲裁模块的审查
  S-02: 涉及敏感操作的工具必须在方案中明确标注"需用户确认"
  S-03: 用户显式指定的工具优先于系统推荐，但安全审查不可跳过
  S-04: 历史经验数据仅用于工具评估，不得包含任何用户个人身份信息
  S-05: 工具参数预校验仅检查参数格式合法性，不得缓存或存储用户的实际参数值
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import math


class SelectorState(Enum):
    WAITING_REQUIREMENT = "waiting_requirement"
    MATCHING = "matching"
    EVALUATING = "evaluating"
    SELECTED = "selected"
    NO_TOOL_AVAILABLE = "no_tool_available"
    SYSTEM_PAUSED = "system_paused"


@dataclass
class StepResourceRequirement:
    step_id: str = ""
    plan_id: str = ""
    required_tool_type: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    deadline_sec: float = 0.0
    user_specified_tool: Optional[str] = None
    allow_degradation: bool = True


@dataclass
class ToolInfo:
    name: str = ""
    description: str = ""
    tool_type: str = ""
    parameters_template: Dict[str, Any] = field(default_factory=dict)
    call_cost: float = 0.0  # 0.0-1.0 归一化成本
    is_online: bool = True
    max_concurrency: int = 10
    current_load: int = 0


@dataclass
class ToolExperience:
    tool_name: str = ""
    success_rate: float = 0.5
    avg_response_ms: float = 500.0
    common_errors: List[str] = field(default_factory=list)
    call_count: int = 0


@dataclass
class CandidateTool:
    tool: ToolInfo = field(default_factory=ToolInfo)
    match_score: float = 0.0
    success_rate: float = 0.5
    cost_score: float = 1.0
    availability_score: float = 1.0
    overall_score: float = 0.0
    params_valid: bool = True
    missing_params: List[str] = field(default_factory=list)
    risk_label: str = ""


@dataclass
class ToolSelectionPlan:
    step_id: str = ""
    primary_tool: Optional[CandidateTool] = None
    backup_tools: List[CandidateTool] = field(default_factory=list)
    estimated_call_cost: float = 0.0
    estimated_success_rate: float = 0.0
    user_confirmation_required: bool = False
    safety_review_pending: bool = True  # 修复：标记需安全审查
    selection_duration_ms: float = 0.0


@dataclass
class NoToolNotice:
    step_id: str = ""
    missing_tool_type: str = ""
    suggestion: str = ""
    can_degrade: bool = True


@dataclass
class SelectorStatus:
    state: SelectorState = SelectorState.WAITING_REQUIREMENT
    total_selections: int = 0
    avg_selection_duration_ms: float = 0.0
    cache_hit_rate: float = 0.0


class ToolSelector:
    # 评估权重
    MATCH_WEIGHT = 0.40
    SUCCESS_WEIGHT = 0.25
    COST_WEIGHT = 0.20
    AVAIL_WEIGHT = 0.15

    # 阈值
    HIGH_SUCCESS_THRESHOLD = 0.90
    LOW_SUCCESS_THRESHOLD = 0.50
    HIGH_RISK_SCORE = 0.50
    QUERY_TIMEOUT_SEC = 2.0
    STATUS_REPORT_INTERVAL_SEC = 60

    # 缓存
    TOOL_CATALOG_CACHE_TTL_SEC = 300

    def __init__(self):
        self.module_id = "ag-ecc-03"
        self.module_name = "工具选择模块"
        self.version = "V1.0"

        self.state = SelectorState.WAITING_REQUIREMENT
        self._total_selections: int = 0
        self._total_selection_time: float = 0.0
        self._cache_hits: int = 0
        self._cached_catalog: Optional[List[ToolInfo]] = None
        self._cached_catalog_time: float = 0.0
        self._last_status_time: float = time.time()
        self._pending_logs: List[Dict[str, Any]] = []

        # 回调注入
        self._query_requirement = None
        self._query_tool_catalog = None
        self._query_tool_experience = None
        self._query_param_validation = None

        self._publish_selection_plan = None
        self._publish_no_tool_notice = None
        self._publish_status_report = None
        self._publish_event_log = None

        print(f"[{self.module_id}] {self.module_name} {self.version} 初始化完成")

    # ========== 回调注入 ==========
    def set_requirement_query(self, callback: Callable[[], Optional[StepResourceRequirement]]):
        self._query_requirement = callback

    def set_tool_catalog_query(self, callback: Callable[[], Optional[List[ToolInfo]]]):
        self._query_tool_catalog = callback

    def set_tool_experience_query(self, callback: Callable[[str, str], Optional[ToolExperience]]):
        self._query_tool_experience = callback

    def set_param_validation_query(self, callback: Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]):
        self._query_param_validation = callback

    def set_selection_plan_publisher(self, callback: Callable[[ToolSelectionPlan], None]):
        self._publish_selection_plan = callback

    def set_no_tool_notice_publisher(self, callback: Callable[[NoToolNotice], None]):
        self._publish_no_tool_notice = callback

    def set_status_report_publisher(self, callback: Callable[[SelectorStatus], None]):
        self._publish_status_report = callback

    def set_event_log_publisher(self, callback: Callable[[Dict[str, Any]], None]):
        self._publish_event_log = callback

    # ========== 主循环 ==========
    def run_selection_cycle(self) -> Optional[ToolSelectionPlan]:
        now = time.time()

        if self.state == SelectorState.SYSTEM_PAUSED:
            return None

        # 定期状态上报
        if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
            self._publish_status()
            self._last_status_time = now

        # 接收步骤资源需求
        requirement = self._query_requirement() if self._query_requirement else None
        if requirement is None:
            return None

        self.state = SelectorState.MATCHING
        start_time = time.time()

        # 用户指定工具优先
        if requirement.user_specified_tool:
            plan = self._build_user_specified_plan(requirement)
            self._finalize_selection(plan, start_time)
            return plan

        # 获取工具目录
        catalog = self._get_tool_catalog()
        if not catalog:
            self.state = SelectorState.NO_TOOL_AVAILABLE
            self._send_no_tool_notice(requirement, "工具注册中心不可用")
            self.state = SelectorState.WAITING_REQUIREMENT
            return None

        # 初筛：按功能匹配度筛选
        candidates = self._initial_filter(catalog, requirement)
        if not candidates:
            self.state = SelectorState.NO_TOOL_AVAILABLE
            self._send_no_tool_notice(requirement, f"无匹配'{requirement.required_tool_type}'的工具")
            self.state = SelectorState.WAITING_REQUIREMENT
            return None

        # 多维评估
        self.state = SelectorState.EVALUATING
        params_all_failed = True
        min_failed_count = float('inf')
        best_failed_candidate = None

        for candidate in candidates:
            # 查询历史经验
            experience = self._query_tool_experience(candidate.tool.name, requirement.required_tool_type) if self._query_tool_experience else None
            if experience:
                candidate.success_rate = experience.success_rate
            else:
                candidate.success_rate = 0.5

            # 参数预校验
            if self._query_param_validation:
                validation = self._query_param_validation(candidate.tool.name, requirement.parameters)
                if validation:
                    candidate.params_valid = validation.get("valid", True)
                    candidate.missing_params = validation.get("missing_params", [])
                    if not candidate.params_valid:
                        failed_count = len(candidate.missing_params)
                        if failed_count < min_failed_count:
                            min_failed_count = failed_count
                            best_failed_candidate = candidate
                else:
                    candidate.params_valid = True
            else:
                candidate.params_valid = True

            if candidate.params_valid:
                params_all_failed = False

            # 计算综合评分（修复：确认cost_score数据源来自实时目录）
            if candidate.tool.call_cost != 0.0 or candidate.tool.name != "":
                candidate.cost_score = max(0.0, 1.0 - candidate.tool.call_cost)
            else:
                candidate.cost_score = 0.5  # 无法获取成本时使用保守估计

            candidate.availability_score = 1.0 if (candidate.tool.is_online and candidate.tool.current_load < candidate.tool.max_concurrency) else 0.0
            candidate.overall_score = (
                self.MATCH_WEIGHT * candidate.match_score +
                self.SUCCESS_WEIGHT * candidate.success_rate +
                self.COST_WEIGHT * candidate.cost_score +
                self.AVAIL_WEIGHT * candidate.availability_score
            )
            candidate.overall_score = round(candidate.overall_score, 3)

            # 风险标记
            if candidate.overall_score < self.LOW_SUCCESS_THRESHOLD:
                candidate.risk_label = "高风险"

        # 参数全部失败时的兜底策略
        if params_all_failed and best_failed_candidate:
            best_failed_candidate.risk_label = "参数需补充"

        # 按综合评分排序（修复：多维评估后必须重新排序）
        candidates.sort(key=lambda c: c.overall_score, reverse=True)

        # 构建选择方案
        self.state = SelectorState.SELECTED
        primary = candidates[0]
        backups = candidates[1:3]  # 修复：简化切片，Python切片越界不报错

        user_confirmation = False
        if primary.risk_label in ("高风险", "参数需补充"):
            user_confirmation = True

        plan = ToolSelectionPlan(
            step_id=requirement.step_id,
            primary_tool=primary,
            backup_tools=backups,
            estimated_call_cost=primary.tool.call_cost,
            estimated_success_rate=primary.success_rate,
            user_confirmation_required=user_confirmation,
            safety_review_pending=True  # 修复：标记需安全审查，由集成层调用ag-ecc-04
        )

        self._finalize_selection(plan, start_time)
        return plan

    # ========== 筛选与评估 ==========
    def _get_tool_catalog(self) -> List[ToolInfo]:
        """获取工具目录，带缓存"""
        now = time.time()
        if self._cached_catalog and (now - self._cached_catalog_time) < self.TOOL_CATALOG_CACHE_TTL_SEC:
            self._cache_hits += 1
            return self._cached_catalog

        if self._query_tool_catalog:
            catalog = self._query_tool_catalog()
            if catalog:
                self._cached_catalog = catalog
                self._cached_catalog_time = now
                return catalog
        return self._cached_catalog or []

    def _initial_filter(self, catalog: List[ToolInfo], requirement: StepResourceRequirement) -> List[CandidateTool]:
        candidates = []
        required_type = requirement.required_tool_type.lower()

        for tool in catalog:
            match = self._calculate_match(tool, required_type)
            if match > 0:
                candidates.append(CandidateTool(
                    tool=tool,
                    match_score=round(match, 3)
                ))

        return candidates

    def _calculate_match(self, tool: ToolInfo, required_type: str) -> float:
        """计算功能匹配度"""
        tool_type_lower = tool.tool_type.lower()
        tool_name_lower = tool.name.lower()
        tool_desc_lower = tool.description.lower()

        if required_type in tool_type_lower:
            return 0.95
        if required_type in tool_name_lower:
            return 0.90
        if required_type in tool_desc_lower:
            return 0.70
        common_keywords = set(required_type.split()) & set(tool_desc_lower.split())
        if common_keywords:
            return 0.50 + 0.10 * len(common_keywords)
        return 0.0

    def _build_user_specified_plan(self, requirement: StepResourceRequirement) -> ToolSelectionPlan:
        """用户指定工具时直接构建方案，但仍标记需安全审查"""
        tool = ToolInfo(name=requirement.user_specified_tool or "unknown", description="用户指定", tool_type=requirement.required_tool_type)
        candidate = CandidateTool(tool=tool, match_score=1.0, success_rate=0.8)
        return ToolSelectionPlan(
            step_id=requirement.step_id,
            primary_tool=candidate,
            estimated_call_cost=0.0,
            estimated_success_rate=0.8,
            user_confirmation_required=True,  # 修复：用户指定工具也需确认
            safety_review_pending=True         # 修复：安全审查不可跳过
        )

    def _send_no_tool_notice(self, requirement: StepResourceRequirement, reason: str):
        if self._publish_no_tool_notice:
            self._publish_no_tool_notice(NoToolNotice(
                step_id=requirement.step_id,
                missing_tool_type=requirement.required_tool_type,
                suggestion=f"建议降级或等待: {reason}",
                can_degrade=requirement.allow_degradation
            ))

    def _finalize_selection(self, plan: ToolSelectionPlan, start_time: float):
        elapsed = (time.time() - start_time) * 1000
        plan.selection_duration_ms = elapsed

        self._total_selections += 1
        self._total_selection_time += elapsed

        if self._publish_selection_plan:
            self._publish_selection_plan(plan)

        self.state = SelectorState.WAITING_REQUIREMENT

    # ========== 辅助 ==========
    def _publish_status(self):
        avg = self._total_selection_time / max(self._total_selections, 1)
        hit_rate = self._cache_hits / max(self._total_selections, 1)
        if self._publish_status_report:
            self._publish_status_report(SelectorStatus(
                state=self.state,
                total_selections=self._total_selections,
                avg_selection_duration_ms=round(avg, 2),
                cache_hit_rate=round(hit_rate, 3)
            ))

    def get_state(self) -> SelectorState:
        return self.state

    def emergency_shutdown(self):
        self.state = SelectorState.SYSTEM_PAUSED
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
    print("  Agent-ecc-brain 工具选择模块 (ag-ecc-03) 演示")
    print("=" * 70)

    selector = ToolSelector()

    selector.set_tool_catalog_query(lambda: [
        ToolInfo(name="weather_api", description="查询天气信息", tool_type="API"),
        ToolInfo(name="search_engine", description="搜索引擎", tool_type="SEARCH"),
        ToolInfo(name="text_generator", description="文本生成器", tool_type="GENERATE"),
    ])

    print_separator("STEP 1: 选择天气查询工具")
    selector.set_requirement_query(lambda: StepResourceRequirement(
        step_id="STEP-01", plan_id="PLAN-01", required_tool_type="API"
    ))
    plan = selector.run_selection_cycle()
    if plan and plan.primary_tool:
        print(f"  主选工具: {plan.primary_tool.tool.name}")
        print(f"  综合评分: {plan.primary_tool.overall_score}")
        print(f"  安全审查待定: {plan.safety_review_pending}")

    print_separator("STEP 2: 用户指定工具（标记需安全审查）")
    selector.set_requirement_query(lambda: StepResourceRequirement(
        step_id="STEP-02", plan_id="PLAN-02",
        required_tool_type="API", user_specified_tool="my_custom_tool"
    ))
    plan = selector.run_selection_cycle()
    if plan and plan.primary_tool:
        print(f"  主选工具: {plan.primary_tool.tool.name} (用户指定)")
        print(f"  需用户确认: {plan.user_confirmation_required}")
        print(f"  安全审查待定: {plan.safety_review_pending}")

    print_separator("STEP 3: 无匹配工具")
    selector.set_requirement_query(lambda: StepResourceRequirement(
        step_id="STEP-03", plan_id="PLAN-03", required_tool_type="UNKNOWN_TYPE"
    ))
    plan = selector.run_selection_cycle()
    if plan is None:
        print(f"  正确返回无工具通知")

    print("\n✅ 工具选择模块演示完成")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("ag-ecc-03 工具选择模块 单元测试")
        print("=" * 60)
        passed, failed = 0, 0

        def setup_selector():
            s = ToolSelector()
            s.set_tool_catalog_query(lambda: [
                ToolInfo(name="weather_api", description="天气API", tool_type="API"),
                ToolInfo(name="search_engine", description="搜索引擎", tool_type="SEARCH"),
            ])
            return s

        # TC-E03-01: 正常匹配工具
        print("\n[TC-E03-01] 正常匹配工具")
        try:
            s = setup_selector()
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T01", plan_id="P01", required_tool_type="API"
            ))
            plan = s.run_selection_cycle()
            assert plan is not None
            assert plan.primary_tool is not None
            assert plan.primary_tool.tool.name == "weather_api"
            assert plan.safety_review_pending is True
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E03-02: 用户指定工具优先
        print("\n[TC-E03-02] 用户指定工具优先")
        try:
            s = setup_selector()
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T02", plan_id="P02", required_tool_type="API", user_specified_tool="user_tool"
            ))
            plan = s.run_selection_cycle()
            assert plan is not None
            assert plan.primary_tool.tool.name == "user_tool"
            assert plan.user_confirmation_required is True
            assert plan.safety_review_pending is True
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E03-03: 无匹配工具
        print("\n[TC-E03-03] 无匹配工具")
        try:
            s = setup_selector()
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T03", plan_id="P03", required_tool_type="NONEXISTENT"
            ))
            plan = s.run_selection_cycle()
            assert plan is None
            assert s.state == SelectorState.WAITING_REQUIREMENT
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E03-04: 工具目录缓存命中
        print("\n[TC-E03-04] 工具目录缓存命中")
        try:
            s = setup_selector()
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T04a", plan_id="P04", required_tool_type="API"
            ))
            s.run_selection_cycle()
            initial_cache_hits = s._cache_hits
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T04b", plan_id="P04", required_tool_type="API"
            ))
            s.run_selection_cycle()
            assert s._cache_hits > initial_cache_hits
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E03-05: 低评分工具风险标记
        print("\n[TC-E03-05] 低评分工具风险标记")
        try:
            s = setup_selector()
            s.set_tool_catalog_query(lambda: [
                ToolInfo(name="risky_tool", description="高风险工具", tool_type="API", call_cost=0.9)
            ])
            s.set_tool_experience_query(lambda tool, task: ToolExperience(tool_name=tool, success_rate=0.3))
            s.set_requirement_query(lambda: StepResourceRequirement(
                step_id="T05", plan_id="P05", required_tool_type="API"
            ))
            plan = s.run_selection_cycle()
            assert plan is not None
            assert plan.user_confirmation_required
            print("   ✅ PASS")
            passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}")
            failed += 1

        # TC-E03-06: 紧急熔断
        print("\n[TC-E03-06] 紧急熔断")
        try:
            s = setup_selector()
            s.emergency_shutdown()
            assert s.state == SelectorState.SYSTEM_PAUSED
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