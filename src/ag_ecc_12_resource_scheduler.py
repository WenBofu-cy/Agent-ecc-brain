#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块编号: ag-ecc-12
模块名称: 资源调度模块
所属分区: 一、认知大脑核心模块
版本：V1.0
原创提出者：文波福

核心职责: 全局中枢与唯一对外网关，统筹资源管理、跨系统通信代理、熔断保护、
          人机主权闭锁、权限管控及全链路审计。不参与认知决策，仅执行资源分配、
          通信代理与安全策略。

安全约束:
  R-01: 唯一对外网关，所有跨系统通信必须经本模块中转
  R-02: 安全仲裁模块下发的熔断/降级/闭锁指令具有最高优先级
  R-03: 外部大模型调用必须经过配额管理，防止恶意或异常的高频调用
  R-04: 所有跨系统通信必须记录完整的审计日志
  R-05: 主权闭锁状态一旦触发，仅可人工解除，任何自动化模块无权恢复自动化操作
  R-06: 系统资源监控数据仅用于内部调度决策，不得泄露给外部系统
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
import logging
import hmac
import hashlib
from collections import deque

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

from memory_bus import Message, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_CRITICAL

logger = logging.getLogger("ag-ecc-12")

if not _HAS_PSUTIL:
    logger.warning("psutil 未安装，将使用默认资源指标。建议: pip install psutil")


class SchedulerState(Enum):
    NORMAL_SCHEDULING = "NORMAL_SCHEDULING"
    RESOURCE_WARNING = "RESOURCE_WARNING"
    RESOURCE_CRITICAL = "RESOURCE_CRITICAL"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    HUMAN_LOCKDOWN = "HUMAN_LOCKDOWN"
    SYSTEM_PAUSED = "SYSTEM_PAUSED"


class DegradeLevel(Enum):
    LEVEL_1 = "一级降级"
    LEVEL_2 = "二级降级"
    LEVEL_3 = "三级降级"


class AllowMsgType(Enum):
    SAFE_CMD = "安全指令"
    CIRCUIT_CONFIRM = "熔断确认"


class MemOpType(Enum):
    WRITE = "write"
    SAVE = "save"
    写入 = "写入"
    保存 = "保存"


@dataclass
class ResourceAllocationResult:
    requester_module: str = ""
    allocation_type: str = ""
    allocated_amount: float = 0.0
    valid_until_sec: float = 300.0
    constraints: Dict[str, Any] = field(default_factory=dict)
    create_time: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


class ResourceScheduler:
    CPU_WARN = 80.0
    CPU_CRITICAL = 95.0
    MEM_WARN = 80.0
    MEM_CRITICAL = 95.0
    STORAGE_WARN = 80.0
    STORAGE_CRITICAL = 95.0

    LLM_DAILY_TOKEN = 100000
    LLM_WARN_RATIO = 0.80
    LLM_CRITICAL_RATIO = 0.95

    MAX_QUEUE = 1000
    STATUS_INTERVAL_SEC = 30
    DAILY_RESET_CHECK_SEC = 300
    ALLOC_CLEAN_INTERVAL_SEC = 600
    RESOURCE_STABLE_COUNT = 3

    UNLOCK_SECRET_KEY = b"ECC-LOCK-SECRET-2026-0610"

    def __init__(self):
        self.module_id = "ag-ecc-12"
        self.version = "V1.0"
        self.state = SchedulerState.NORMAL_SCHEDULING
        self.bus = None
        self.external_bus = None
        self.cerebellum_bus = None

        self._resource_usage: Dict[str, float] = {}
        self._llm_tokens_used = 0
        self._llm_warn_sent = False
        self._today_comm_count = 0
        self._alert_count = 0
        self._last_status = 0.0
        self._last_daily_reset_check = 0.0
        self._last_alloc_clean = 0.0
        self._current_utc_date = time.strftime("%Y-%m-%d", time.gmtime())

        self._prev_resource_state = SchedulerState.NORMAL_SCHEDULING
        self._state_stable_counter = 0
        self._mem_write_limited = False

        self._message_queue: deque = deque(maxlen=self.MAX_QUEUE)
        self._allocations: Dict[str, ResourceAllocationResult] = {}

        logger.info("资源调度模块初始化完成")

    def handle_message(self, msg: Message):
        if len(self._message_queue) >= self.MAX_QUEUE:
            if msg.priority not in (PRIORITY_CRITICAL, PRIORITY_HIGH):
                self._log_audit("QUEUE_FULL_DROP", {"topic": msg.topic, "source": msg.source_module})
                return
            else:
                try:
                    removed = False
                    for idx, old_msg in enumerate(self._message_queue):
                        if old_msg.priority not in (PRIORITY_CRITICAL, PRIORITY_HIGH):
                            del self._message_queue[idx]
                            removed = True
                            self._log_audit("QUEUE_FORCED_REMOVE", {"topic": old_msg.topic, "source": old_msg.source_module})
                            break
                    if not removed:
                        self._log_audit("QUEUE_FULL_CRITICAL_DROP", {"topic": msg.topic, "source": msg.source_module})
                        return
                except Exception:
                    self._message_queue.popleft()
        self._message_queue.append(msg)

    def resource_scheduler_main_loop(self):
        try:
            if self.state == SchedulerState.SYSTEM_PAUSED:
                return

            now = time.time()

            if now - self._last_daily_reset_check >= self.DAILY_RESET_CHECK_SEC:
                self._check_daily_reset_utc()
                self._last_daily_reset_check = now

            if now - self._last_alloc_clean >= self.ALLOC_CLEAN_INTERVAL_SEC:
                self._clean_expired_allocations(now)
                self._last_alloc_clean = now

            if now - self._last_status >= self.STATUS_INTERVAL_SEC:
                self._publish_status()
                self._last_status = now

            while self._message_queue:
                msg = self._message_queue.popleft()
                self._dispatch_message(msg)

            self._evaluate_resource_state(now)

        except Exception as e:
            logger.error(f"主循环运行异常: {str(e)}", exc_info=True)

    def _dispatch_message(self, msg: Message):
        try:
            topic = msg.topic
            corr_id = msg.correlation_id
            src_module = msg.source_module

            if topic == "ag-ecc-12.degrade_command":
                self._handle_degrade_command(msg.data)
                return
            if topic == "ag-ecc-12.lockdown_command":
                self._handle_lockdown_command(msg.data)
                return
            if topic == "ag-ecc-12.release_lockdown":
                self._handle_release_lockdown(msg.data)
                return

            if topic in ("ag-ecc-12.shutdown", "ag-ecc-12.pause"):
                self.emergency_shutdown()
                return
            if topic == "ag-ecc-12.resume":
                if self.state == SchedulerState.HUMAN_LOCKDOWN:
                    logger.warning("主权闭锁状态下拒绝自动恢复指令")
                    return
                if self.state == SchedulerState.SYSTEM_PAUSED:
                    self.state = SchedulerState.NORMAL_SCHEDULING
                    logger.info("资源调度模块恢复服务")
                return

            if topic == "ag-ecc-12.cross_system_request":
                self._handle_cross_system(msg.data, src_module, corr_id)
                return
            if topic == "ag-ecc-12.query_resource":
                self._send_resource_reply(src_module, corr_id)
                return
            if topic == "ag-ecc-12.request_allocation":
                self._handle_allocation_request(msg)
                return

            if topic.startswith("ag-mem-"):
                self._forward_to_internal(topic, msg.data, corr_id)
                return
            if topic.startswith("ag-mcc-"):
                self._forward_to_internal(topic, msg.data, corr_id)
                return

            self._log_audit("UNKNOWN", {"topic": topic, "source": src_module})

        except Exception as e:
            logger.error(f"消息分发异常 topic={msg.topic}: {str(e)}", exc_info=True)

    def _handle_degrade_command(self, data: Dict[str, Any]):
        level = data.get("target_level", 1)
        reason = data.get("reason", "")
        if level == 3:
            self.state = SchedulerState.CIRCUIT_BREAKER
            self._broadcast_internal("degrade_level_3", {"reason": reason})
        elif level == 2:
            self._mem_write_limited = True
            self.state = SchedulerState.RESOURCE_CRITICAL
            self._broadcast_internal("degrade_level_2", {})
        else:
            if self.state not in (SchedulerState.CIRCUIT_BREAKER, SchedulerState.HUMAN_LOCKDOWN):
                self.state = SchedulerState.RESOURCE_WARNING
            self._broadcast_internal("degrade_level_1", {})

    def _handle_lockdown_command(self, data: Dict[str, Any]):
        self.state = SchedulerState.HUMAN_LOCKDOWN
        self._broadcast_internal("lockdown", {"reason": data.get("reason")})
        self._log_audit("HUMAN_LOCKDOWN", {"reason": data.get("reason")})

    def _handle_release_lockdown(self, data: Dict[str, Any]):
        if self.state != SchedulerState.HUMAN_LOCKDOWN:
            logger.warning("当前非闭锁状态，忽略解锁指令")
            return

        token = data.get("token", "")
        confirm_count = data.get("confirm_count", 0)
        operator = data.get("operator", "unknown")
        op_ip = data.get("operator_ip", "0.0.0.0")
        nonce = data.get("nonce", "")

        if not all([token, nonce]) or confirm_count < 2:
            self._log_audit("RELEASE_LOCKDOWN_FAILED", {
                "reason": "参数缺失或双重确认不足",
                "operator": operator,
                "ip": op_ip
            })
            logger.warning("主权闭锁解除失败：参数非法")
            return

        sign_content = f"{operator}{nonce}{confirm_count}"
        calc_hmac = hmac.new(
            self.UNLOCK_SECRET_KEY,
            sign_content.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calc_hmac, token):
            self._log_audit("RELEASE_LOCKDOWN_FAILED", {
                "reason": "签名校验失败",
                "operator": operator,
                "ip": op_ip
            })
            logger.warning("主权闭锁解除失败：签名无效")
            return

        self.state = SchedulerState.NORMAL_SCHEDULING
        self._mem_write_limited = False
        self._log_audit("RELEASE_LOCKDOWN", {
            "operator": operator,
            "operator_ip": op_ip,
            "nonce": nonce
        })
        logger.info(f"主权闭锁已由人工[{operator}]解除，恢复正常调度")

    def _handle_cross_system(self, data: Dict[str, Any], source: str, corr_id: str):
        target = data.get("target_system", "")
        payload = data.get("payload", {})
        msg_type = data.get("message_type", "")

        allow_types = {AllowMsgType.SAFE_CMD.value, AllowMsgType.CIRCUIT_CONFIRM.value}
        if self.state in (SchedulerState.CIRCUIT_BREAKER, SchedulerState.HUMAN_LOCKDOWN):
            if msg_type not in allow_types:
                self._log_audit("REJECTED_LOCKDOWN", {"source": source, "target": target})
                return

        if target == "MLNF-Mem":
            if self._mem_write_limited and msg_type in (
                MemOpType.WRITE.value, MemOpType.SAVE.value,
                MemOpType.写入.value, MemOpType.保存.value
            ):
                self._log_audit("WRITE_LIMITED", {"source": source})
                return
            if self.external_bus:
                self.external_bus.publish(
                    topic=f"ag-mem-01.{msg_type}",
                    source_module=self.module_id,
                    data=payload,
                    target_module="ag-mem-01",
                    correlation_id=corr_id,
                    priority=PRIORITY_NORMAL
                )

        elif target == "MCC":
            if self.cerebellum_bus:
                self.cerebellum_bus.publish(
                    topic=f"ag-mcc-01.{msg_type}",
                    source_module=self.module_id,
                    data=payload,
                    target_module="ag-mcc-01",
                    correlation_id=corr_id,
                    priority=PRIORITY_NORMAL
                )

        elif target == "大模型":
            self._handle_llm_call_real(payload, source)

        self._today_comm_count += 1
        self._log_audit("CROSS_SYSTEM", {"source": source, "target": target, "type": msg_type})

    def _handle_llm_call_real(self, payload: Dict[str, Any], source: str):
        warn_lim = int(self.LLM_DAILY_TOKEN * self.LLM_WARN_RATIO)
        crit_lim = int(self.LLM_DAILY_TOKEN * self.LLM_CRITICAL_RATIO)

        if self._llm_tokens_used >= crit_lim:
            self._log_audit("LLM_QUOTA_EXHAUSTED", {"used": self._llm_tokens_used})
            return

        if self._llm_tokens_used >= warn_lim and not self._llm_warn_sent:
            self._llm_warn_sent = True
            self._log_audit("LLM_QUOTA_WARNING", {"used": self._llm_tokens_used})

        self._log_audit("LLM_REQUEST", {"source": source, "payload_snapshot": str(payload)[:200]})

    def llm_add_tokens(self, token_num: int):
        if not isinstance(token_num, int) or token_num <= 0:
            return
        self._llm_tokens_used += token_num
        self._log_audit("LLM_TOKEN_CONSUME", {"tokens": token_num, "total_used": self._llm_tokens_used})

    def _check_daily_reset_utc(self):
        today_utc = time.strftime("%Y-%m-%d", time.gmtime())
        if today_utc != self._current_utc_date:
            self._llm_tokens_used = 0
            self._llm_warn_sent = False
            self._current_utc_date = today_utc
            logger.info("大模型日配额(UTC)已自动重置")

    def _send_resource_reply(self, requester: str, correlation_id: str = ""):
        if not self.bus:
            return
        data = {
            "cpu_usage_pct": self._resource_usage.get("cpu", 30.0),
            "memory_usage_pct": self._resource_usage.get("mem", 40.0),
            "storage_usage_pct": self._resource_usage.get("storage", 20.0),
            "active_sessions": 0,
        }
        self.bus.publish(
            topic=f"{requester}.resource_response",
            source_module=self.module_id,
            data=data,
            target_module=requester,
            correlation_id=correlation_id,
            priority=PRIORITY_NORMAL
        )

    def _handle_allocation_request(self, msg: Message):
        req = msg.data
        requester = msg.source_module
        alloc_type = req.get("type", "default")
        corr_id = msg.correlation_id

        cpu = self._resource_usage.get("cpu", 30.0)
        mem = self._resource_usage.get("mem", 40.0)
        allocated = 0.3 if (cpu > self.CPU_WARN or mem > self.MEM_WARN) else 0.8

        result = ResourceAllocationResult(
            requester_module=requester,
            allocation_type=alloc_type,
            allocated_amount=allocated,
            valid_until_sec=300.0,
            constraints={"max_concurrency": 5}
        )
        if self.bus:
            self.bus.publish(
                topic=f"{requester}.allocation_response",
                source_module=self.module_id,
                data=result.to_dict(),
                target_module=requester,
                correlation_id=corr_id,
                priority=PRIORITY_NORMAL
            )
        self._allocations[requester] = result

    def _clean_expired_allocations(self, now: float):
        expired_keys = []
        for key, alloc in self._allocations.items():
            if now - alloc.create_time > alloc.valid_until_sec:
                expired_keys.append(key)
        for key in expired_keys:
            self._allocations.pop(key, None)
        if expired_keys:
            logger.debug(f"清理过期资源分配记录: {len(expired_keys)} 条")

    def _evaluate_resource_state(self, now: float):
        if _HAS_PSUTIL and psutil:
            try:
                cpu_usage = psutil.cpu_percent(interval=None)
                mem_info = psutil.virtual_memory()
                mem_usage = mem_info.percent
                disk_info = psutil.disk_usage("/")
                storage_usage = disk_info.percent
            except Exception as e:
                logger.warning(f"psutil 采集失败: {e}")
                cpu_usage = 0.0
                mem_usage = 0.0
                storage_usage = 0.0
        else:
            cpu_usage = 0.0
            mem_usage = 0.0
            storage_usage = 0.0

        if not self._resource_usage:
            self._resource_usage = {
                "cpu": cpu_usage,
                "mem": mem_usage,
                "storage": storage_usage
            }

        cpu = self._resource_usage.get("cpu", 0.0)
        mem = self._resource_usage.get("mem", 0.0)
        storage = self._resource_usage.get("storage", 0.0)

        if cpu >= self.CPU_CRITICAL or mem >= self.MEM_CRITICAL or storage >= self.STORAGE_CRITICAL:
            current_state = SchedulerState.RESOURCE_CRITICAL
        elif cpu >= self.CPU_WARN or mem >= self.MEM_WARN or storage >= self.STORAGE_WARN:
            current_state = SchedulerState.RESOURCE_WARNING
        else:
            current_state = SchedulerState.NORMAL_SCHEDULING

        if current_state == self._prev_resource_state:
            self._state_stable_counter += 1
        else:
            self._state_stable_counter = 0
            self._prev_resource_state = current_state

        if (self._state_stable_counter >= self.RESOURCE_STABLE_COUNT
                and self.state not in (SchedulerState.CIRCUIT_BREAKER, SchedulerState.HUMAN_LOCKDOWN, SchedulerState.SYSTEM_PAUSED)
                and self.state != current_state):
            self.state = current_state
            self._mem_write_limited = (current_state != SchedulerState.NORMAL_SCHEDULING)
            self._broadcast_internal("resource_state_change", {"new_state": current_state.value})
            logger.info(f"资源状态切换为: {current_state.value}")

    def update_resource_metrics(self, cpu: float, mem: float, storage: float):
        self._resource_usage = {"cpu": cpu, "mem": mem, "storage": storage}

    def _broadcast_internal(self, event: str, data: Dict[str, Any]):
        if self.bus:
            self.bus.publish(
                topic=f"ag-ecc-12.broadcast.{event}",
                source_module=self.module_id,
                data=data,
                priority=PRIORITY_HIGH
            )

    def _forward_to_internal(self, topic: str, data: Any, corr_id: str):
        if not self.bus:
            return
        parts = topic.split('.')
        if len(parts) < 2 or not parts[0].startswith("ag-"):
            logger.warning(f"非法Topic格式，放弃转发: {topic}")
            self._log_audit("FORWARD_FAILED", {"topic": topic, "reason": "格式非法"})
            return
        target_module = parts[0]
        self.bus.publish(
            topic=topic,
            source_module=self.module_id,
            data=data,
            target_module=target_module,
            correlation_id=corr_id,
            priority=PRIORITY_NORMAL
        )

    def _log_audit(self, event_type: str, details: Dict[str, Any]):
        if self.state == SchedulerState.SYSTEM_PAUSED:
            return
        entry = {
            "event_type": event_type,
            "details": details,
            "timestamp": time.time()
        }
        if self.bus:
            self.bus.publish(
                topic="ag-mem-51.audit_log",
                source_module=self.module_id,
                data=entry,
                target_module="ag-mem-51",
                priority=PRIORITY_LOW
            )

    def _publish_status(self):
        if self.state == SchedulerState.SYSTEM_PAUSED or not self.bus:
            return
        self.bus.publish(
            topic="ag-ecc-12.scheduler_status",
            source_module=self.module_id,
            data={
                "state": self.state.value,
                "cpu": self._resource_usage.get("cpu", 0),
                "mem": self._resource_usage.get("mem", 0),
                "storage": self._resource_usage.get("storage", 0),
                "comm_today": self._today_comm_count,
                "alerts": self._alert_count,
                "llm_tokens_used": self._llm_tokens_used,
            },
            target_module="ag-ecc-12",
            priority=PRIORITY_LOW
        )

    def emergency_shutdown(self):
        self.state = SchedulerState.SYSTEM_PAUSED
        logger.info("资源调度模块已暂停")

    def get_state(self) -> SchedulerState:
        return self.state