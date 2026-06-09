#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-03
模块名称: 工具选择模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责:
  接收 ag-ecc-02 下发的步骤资源需求，在工具注册中心（ag-mcc-04）中检索匹配工具，
  综合评估功能匹配度、调用成本、历史成功率与可用性，输出最优工具选择方案。
  为 ag-ecc-02 提供工具能力约束查询，辅助任务规划。
  不参与工具的实际调用执行，仅负责工具的选择与推荐。

依赖模块:
  ag-ecc-02, ag-ecc-05, ag-ecc-12(网关), ag-mcc-04(通过网关), ag-mcc-05(通过网关)
被依赖模块:
  ag-ecc-02, ag-ecc-04, ag-ecc-12

安全约束:
  S-01: 工具选择方案在下发执行前必须通过 ag-ecc-04 安全仲裁模块的审查
  S-02: 涉及敏感操作的工具必须在方案中明确标注"需用户确认"
  S-03: 用户显式指定的工具优先于系统推荐，但安全审查不可跳过
  S-04: 历史经验数据仅用于工具评估，不得包含任何用户个人身份信息
  S-05: 工具参数预校验仅检查参数格式合法性，不得缓存或存储用户的实际参数值
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, fields
from enum import Enum
import time
import uuid
import logging

from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-03")


# ==================== 状态与类型定义 ====================
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResourceRequirement":
        """过滤未知字段，安全反序列化"""
        field_names = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data)


@dataclass
class ToolInfo:
    name: str = ""
    description: str = ""
    tool_type: str = ""
    parameters_template: Dict[str, Any] = field(default_factory=dict)
    call_cost: float = 0.0
    is_online: bool = True
    max_concurrency: int = 10
    current_load: int = 0
    safety_level: str = "safe"  # safe / sensitive / critical


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
    plan_id: str = ""
    primary_tool: Optional[CandidateTool] = None
    backup_tools: List[CandidateTool] = field(default_factory=list)
    estimated_call_cost: float = 0.0
    estimated_success_rate: float = 0.0
    user_confirmation_required: bool = False
    safety_review_pending: bool = True
    selection_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "plan_id": self.plan_id,
            "primary_tool": self.primary_tool.tool.name if self.primary_tool else "",
            "backup_tools": [bt.tool.name for bt in self.backup_tools],
            "overall_score": self.primary_tool.overall_score if self.primary_tool else 0.0,
            "estimated_call_cost": self.estimated_call_cost,
            "estimated_success_rate": self.estimated_success_rate,
            "user_confirmation_required": self.user_confirmation_required,
            "safety_review_pending": self.safety_review_pending,
            "selection_duration_ms": self.selection_duration_ms,
        }


class ToolSelector:
    """工具选择模块 V1.0"""

    # 评估权重
    MATCH_WEIGHT = 0.40
    SUCCESS_WEIGHT = 0.25
    COST_WEIGHT = 0.20
    AVAIL_WEIGHT = 0.15

    HIGH_SUCCESS_THRESHOLD = 0.90
    LOW_SUCCESS_THRESHOLD = 0.50
    TOOL_CATALOG_CACHE_TTL_SEC = 300
    STATUS_REPORT_INTERVAL_SEC = 60
    NO_TOOL_RECOVERY_SEC = 30  # 无可用工具状态持续30秒后自动恢复

    # 敏感工具名清单（硬编码保护，后续可从安全规则库同步）
    SENSITIVE_TOOLS = {
        "delete_file", "shell_exec", "system_config", "db_write",
        "sudo", "payment_api", "read_contacts", "get_location",
        "browser_history", "read_messages"
    }

    def __init__(self):
        self.module_id = "ag-ecc-03"
        self.version = "V1.0"
        self.state = SelectorState.WAITING_REQUIREMENT
        self.bus = None  # 由主入口注入 InternalBus

        # 内部队列
        self._requirement_buffer: List[StepResourceRequirement] = []
        self._selection_count = 0
        self._total_selection_time = 0.0
        self._last_status_time = time.time()

        # 工具目录缓存
        self._cached_catalog: Optional[List[ToolInfo]] = None
        self._catalog_cache_time = 0.0
        self._cache_hits = 0

        # 无可用工具状态计时
        self._no_tool_start_time: float = 0.0

        logger.info("工具选择模块初始化完成")

    def handle_message(self, msg: Message):
        """接收总线消息"""
        try:
            topic = msg.topic

            if topic == "ag-ecc-03.step_requirement":
                req = StepResourceRequirement.from_dict(msg.data)
                self._requirement_buffer.append(req)
                logger.info(f"收到步骤需求: {req.step_id} 类型={req.required_tool_type}")

            elif topic == "ag-ecc-03.query_constraints":
                self._handle_constraints_query(msg)

            elif topic == "ag-ecc-03.shutdown":
                self.emergency_shutdown()

            elif topic == "ag-ecc-12.shutdown":
                self.emergency_shutdown()

            elif topic == "ag-ecc-03.resume":
                if self.state == SelectorState.SYSTEM_PAUSED:
                    self.state = SelectorState.WAITING_REQUIREMENT
                    logger.info("恢复服务")
            else:
                logger.debug(f"忽略不相关消息: {topic}")

        except Exception as e:
            logger.error(f"处理消息异常: {str(e)}", exc_info=True)

    # ====================== 主循环（CPEC 对齐） ======================
    def tool_selector_main_loop(self):
        """主循环，CPEC 规定的方法名"""
        if self.state == SelectorState.SYSTEM_PAUSED:
            return

        try:
            now = time.time()

            # 从无工具状态自动恢复
            if (self.state == SelectorState.NO_TOOL_AVAILABLE and
                (now - self._no_tool_start_time) > self.NO_TOOL_RECOVERY_SEC):
                self.state = SelectorState.WAITING_REQUIREMENT
                logger.info("无工具状态超时，自动恢复至等待需求")

            if now - self._last_status_time >= self.STATUS_REPORT_INTERVAL_SEC:
                self._publish_status()
                self._last_status_time = now

            if self._requirement_buffer and self.state == SelectorState.WAITING_REQUIREMENT:
                req = self._requirement_buffer.pop(0)
                self._process_requirement(req)

        except Exception as e:
            logger.error(f"主循环异常: {str(e)}", exc_info=True)

    def _process_requirement(self, req: StepResourceRequirement):
        """处理单个步骤需求"""
        self.state = SelectorState.MATCHING
        start_time = time.time()

        # 用户指定工具优先
        if req.user_specified_tool:
            plan = self._build_user_specified_plan(req)
            self._finalize_and_publish(plan, start_time)
            return

        # 获取工具目录
        catalog = self._query_tool_catalog()
        if not catalog:
            self._send_no_tool_notice(req, "工具注册中心不可用")
            self._enter_no_tool_state()
            return

        # 初筛
        candidates = self._initial_filter(catalog, req)
        if not candidates:
            self._send_no_tool_notice(req, f"无匹配'{req.required_tool_type}'的工具")
            self._enter_no_tool_state()
            return

        # 快速路径
        fast_candidate = None
        for c in candidates:
            exp = self._query_tool_experience(c.tool.name, req.required_tool_type)
            if exp and exp.get("success_rate", 0) >= self.HIGH_SUCCESS_THRESHOLD:
                fast_candidate = c
                break
        if fast_candidate:
            plan = ToolSelectionPlan(
                step_id=req.step_id,
                plan_id=req.plan_id,
                primary_tool=fast_candidate,
                estimated_success_rate=fast_candidate.success_rate,
                safety_review_pending=True
            )
            self._apply_safety_flags(plan)
            self._finalize_and_publish(plan, start_time)
            return

        # 多维评估
        self.state = SelectorState.EVALUATING
        for c in candidates:
            exp = self._query_tool_experience(c.tool.name, req.required_tool_type)
            c.success_rate = exp.get("success_rate", 0.5) if exp else 0.5
            validation = self._validate_params(c.tool.name, req.parameters)
            if validation:
                c.params_valid = validation.get("valid", True)
                c.missing_params = validation.get("missing_params", [])
            c.cost_score = max(0.0, 1.0 - c.tool.call_cost) if c.tool.call_cost > 0 else 0.5
            c.availability_score = 1.0 if (c.tool.is_online and c.tool.current_load < c.tool.max_concurrency) else 0.0
            c.overall_score = (
                self.MATCH_WEIGHT * c.match_score +
                self.SUCCESS_WEIGHT * c.success_rate +
                self.COST_WEIGHT * c.cost_score +
                self.AVAIL_WEIGHT * c.availability_score
            )
            if not c.params_valid:
                c.risk_label = "参数需补充"
            elif c.overall_score < self.LOW_SUCCESS_THRESHOLD:
                c.risk_label = "高风险"

        candidates.sort(key=lambda c: c.overall_score, reverse=True)
        primary = candidates[0]
        backups = candidates[1:3] if len(candidates) > 1 else []

        # 基础用户确认标记
        user_confirm = primary.risk_label in ("高风险", "参数需补充")
        plan = ToolSelectionPlan(
            step_id=req.step_id,
            plan_id=req.plan_id,
            primary_tool=primary,
            backup_tools=backups,
            estimated_call_cost=primary.tool.call_cost,
            estimated_success_rate=primary.success_rate,
            user_confirmation_required=user_confirm,
            safety_review_pending=True
        )
        self._apply_safety_flags(plan)
        self._finalize_and_publish(plan, start_time)

    def _apply_safety_flags(self, plan: ToolSelectionPlan):
        """应用安全标注：若工具为敏感操作，强制用户确认"""
        if not plan.primary_tool:
            return
        tool_name = plan.primary_tool.tool.name
        if plan.primary_tool.tool.safety_level in ("sensitive", "critical") or tool_name in self.SENSITIVE_TOOLS:
            plan.user_confirmation_required = True
            plan.primary_tool.risk_label = "敏感操作"

    def _enter_no_tool_state(self):
        self.state = SelectorState.NO_TOOL_AVAILABLE
        self._no_tool_start_time = time.time()

    def _finalize_and_publish(self, plan: ToolSelectionPlan, start_time: float):
        plan.selection_duration_ms = round((time.time() - start_time) * 1000, 2)
        self._selection_count += 1
        self._total_selection_time += plan.selection_duration_ms

        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="tool_selection",
                source_module=self.module_id,
                data=plan.to_dict(),
                priority=PRIORITY_HIGH
            )
            self.bus.publish_to_module(
                target_module="ag-ecc-04",
                event_type="review_request",
                source_module=self.module_id,
                data={
                    "step_id": plan.step_id,
                    "plan_id": plan.plan_id,
                    "tool_name": plan.primary_tool.tool.name if plan.primary_tool else "",
                    "risk_label": plan.primary_tool.risk_label if plan.primary_tool else "",
                    "user_confirmation_required": plan.user_confirmation_required,
                },
                priority=PRIORITY_HIGH
            )

        self.state = SelectorState.WAITING_REQUIREMENT

    # ====================== 通信方法 ======================
    def _send_cross_system_request(self, target_system: str, action: str, params: Dict[str, Any], timeout_ms: int = 2000) -> Optional[Dict[str, Any]]:
        """通过 ag-ecc-12 发送通用跨系统请求（仅用于外部MCC系统）"""
        if not self.bus:
            return None
        resp = self.bus.request(
            topic="ag-ecc-12.cross_system_request",
            source_module=self.module_id,
            data={
                "target_system": target_system,
                "action": action,
                "params": params,
            },
            target_module="ag-ecc-12",
            timeout_ms=timeout_ms
        )
        return resp.data if resp else None

    def _query_tool_catalog(self) -> List[ToolInfo]:
        now = time.time()
        if self._cached_catalog and (now - self._catalog_cache_time) < self.TOOL_CATALOG_CACHE_TTL_SEC:
            self._cache_hits += 1
            return self._cached_catalog
        data = self._send_cross_system_request("ag-mcc-04", "query_tool_catalog", {}, timeout_ms=2000)
        if data:
            catalog = [ToolInfo(**t) for t in data.get("tools", [])]
            self._cached_catalog = catalog
            self._catalog_cache_time = now
            return catalog
        return self._cached_catalog or []

    def _query_tool_experience(self, tool_name: str, task_type: str) -> Optional[Dict[str, Any]]:
        """调用内部模块ag-ecc-05，直接使用内部总线"""
        if not self.bus:
            return None
        resp = self.bus.request(
            topic="ag-ecc-05.query_tool_experience",
            source_module=self.module_id,
            data={"tool_name": tool_name, "task_type": task_type},
            target_module="ag-ecc-05",
            timeout_ms=1000
        )
        return resp.data if resp else None

    def _validate_params(self, tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._send_cross_system_request("ag-mcc-05", "validate_params", {"tool_name": tool_name, "parameters": params}, timeout_ms=1500)

    def _send_no_tool_notice(self, req: StepResourceRequirement, reason: str):
        if self.bus:
            self.bus.publish_to_module(
                target_module="ag-ecc-02",
                event_type="no_tool_available",
                source_module=self.module_id,
                data={
                    "step_id": req.step_id,
                    "plan_id": req.plan_id,
                    "required_tool_type": req.required_tool_type,
                    "reason": reason,
                    "can_degrade": req.allow_degradation
                },
                priority=PRIORITY_NORMAL
            )

    def _handle_constraints_query(self, msg: Message):
        catalog = self._cached_catalog or []
        constraints = {
            "available_tools": [t.name for t in catalog if t.is_online],
            "unavailable_tools": [t.name for t in catalog if not t.is_online],
            "tool_types": list(set(t.tool_type for t in catalog)),
            "max_concurrency": {t.name: t.max_concurrency for t in catalog},
            "current_load": {t.name: t.current_load for t in catalog},
        }
        if self.bus:
            self.bus.publish_reply(
                topic="ag-ecc-02.constraints_response",
                source_module=self.module_id,
                data=constraints,
                correlation_id=msg.correlation_id,
                target_module=msg.source_module,
                priority=PRIORITY_NORMAL
            )

    def _publish_status(self):
        if self.bus:
            avg = self._total_selection_time / max(self._selection_count, 1)
            self.bus.publish_to_module(
                target_module="ag-ecc-12",
                event_type="selector_status",
                source_module=self.module_id,
                data={
                    "state": self.state.value,
                    "total_selections": self._selection_count,
                    "avg_duration_ms": round(avg, 2),
                    "cache_hit_rate": round(self._cache_hits / max(self._selection_count, 1), 3)
                },
                priority=PRIORITY_NORMAL
            )

    # ====================== 筛选与评估算法 ======================
    def _initial_filter(self, catalog: List[ToolInfo], req: StepResourceRequirement) -> List[CandidateTool]:
        candidates = []
        required_type = req.required_tool_type.lower()
        for tool in catalog:
            match = self._calculate_match(tool, required_type)
            if match > 0:
                candidates.append(CandidateTool(tool=tool, match_score=round(match, 3)))
        return candidates

    def _calculate_match(self, tool: ToolInfo, required_type: str) -> float:
        # 增加边界保护：避免 None 值引发 AttributeError
        tool_type_lower = (tool.tool_type or "").lower()
        tool_name_lower = (tool.name or "").lower()
        tool_desc_lower = (tool.description or "").lower()
        required_type = required_type or ""

        if required_type and required_type in tool_type_lower:
            return 0.95
        if required_type and required_type in tool_name_lower:
            return 0.90
        if required_type and required_type in tool_desc_lower:
            return 0.70
        # 关键词匹配
        if required_type:
            common_keywords = set(required_type.split()) & set(tool_desc_lower.split())
            if common_keywords:
                return 0.50 + 0.10 * len(common_keywords)
        return 0.0

    def _build_user_specified_plan(self, req: StepResourceRequirement) -> ToolSelectionPlan:
        """用户指定工具优先，但尝试从注册中心获取真实信息以提升可靠性"""
        tool_name = req.user_specified_tool or "unknown"
        tool_info = None
        risk_label = ""

        # 尝试查询工具目录，获取真实工具信息
        catalog = self._query_tool_catalog()
        if catalog:
            for t in catalog:
                if t.name == tool_name:
                    tool_info = t
                    break
        if not tool_info:
            # 注册中心未找到，构造基本信息并标记风险
            tool_info = ToolInfo(name=tool_name, description="用户指定但未在注册中心找到",
                                 tool_type=req.required_tool_type)
            risk_label = "用户指定工具未注册"
            logger.warning(f"用户指定的工具 '{tool_name}' 未在注册中心找到")

        candidate = CandidateTool(tool=tool_info, match_score=1.0, success_rate=0.8,
                                  risk_label=risk_label)
        plan = ToolSelectionPlan(
            step_id=req.step_id,
            plan_id=req.plan_id,
            primary_tool=candidate,
            user_confirmation_required=True,  # 用户指定工具始终需要确认
            safety_review_pending=True
        )
        self._apply_safety_flags(plan)
        return plan

    def emergency_shutdown(self):
        self.state = SelectorState.SYSTEM_PAUSED
        logger.info("工具选择模块已暂停")

    def get_state(self) -> SelectorState:
        return self.state


if __name__ == "__main__":
    print("工具选择模块 V1.0 已加载")