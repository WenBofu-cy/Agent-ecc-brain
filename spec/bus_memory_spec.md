# CerebellumBus 总线报文规范 V1.1
**EM-Core Agent · 认知层与执行层指令交互标准**
**版本**：V1.1 ｜ **日期**：2026-06-21
**适用中枢**：ECC（认知大脑） ↔ MCC（执行小脑）
**架构同源**：EM-Core HR人形机器人 /EM-Core AD自动驾驶

## 一、总线定位
CerebellumBus 是 ECC 认知大脑与 MCC 执行小脑唯一的指令通信通道。任务下发、DAG并行调度、故障回执、熔断信号、资源降级同步、会话状态同步及跨设备会话路由全部经由本总线流转。

**核心约束：**
1. ECC-12 网关为 REQUEST 报文唯一发送端；RESPONSE 与 NOTIFY 报文由 MCC 各模块主动上报，不受此限。
2. 所有业务指令采用请求-回执双报文模型；熔断、降级、心跳、跨设备同步为单向 NOTIFY 报文。
3. 多会话报文基于 session_id 分片隔离处理，单会话 DAG 任务有序解析。
4. ECC 下发 DAG 任务 REQUEST 报文须携带有效 sign_ecc05。MCC-02 校验 sign_ecc05 通过后即时生成 sign_mcc02 存入 DAG 上下文缓存，双签名同步用于回执、熔断、告警类报文，缺失任一签名直接丢弃并返回 REJECT 回执，写入审计日志。
5. L3 永久拦截级任务在 ECC-12 网关预处理阶段直接拦截，不下发至总线。若因异常时序 L3 报文已进入 CerebellumBus，MCC-02 校验 sign_ecc05 时识别到 L3 标记，立即丢弃且严禁入队，仅上报安全告警。

## 二、报文通用格式
### 2.1 通用报文头
```json
{
  "header": {
    "msg_id": "cere-20260621-152010-0001",
    "msg_type": "REQUEST | RESPONSE | NOTIFY",
    "source": "ECC-12",
    "target": "MCC-01",
    "session_id": "session_x",
    "timestamp": "2026-06-21T15:20:10.000Z",
    "ext_version": "1.1"
  },
  "body": {}
}
```

### 2.2 头部字段定义
- **msg_id**：string，全局唯一报文ID，格式 `cere-{date}-{time}-{seq}`，REQUEST、TASK_FEEDBACK 报文用于幂等去重。
- **msg_type**：enum，REQUEST（下发任务） / RESPONSE（回执结果） / NOTIFY（单向通知）。
- **source**：string，报文发送方模块编号。REQUEST 固定为 ECC-12；RESPONSE 为 MCC-36 或对应回执模块；NOTIFY 为 MCC-33/MCC-37/MCC-04 等。
- **target**：string，报文接收方模块编号。
- **session_id**：string，会话隔离标识，锁、并发、回执路由核心字段。
- **timestamp**：ISO8601 格式，所有时间戳必须严格保留三位毫秒级精度（.sssZ），禁止省略。仅用于日志排序与防重放校验。
- **ext_version**：string，协议版本，固定 "1.1"。主版本不同直接丢弃，次版本向前兼容。

### 2.3 标准回执报文模板
```json
{
  "header": {
    "msg_id": "cere-20260621-152010-0002",
    "msg_type": "RESPONSE",
    "source": "MCC-36",
    "target": "ECC-12",
    "session_id": "session_x",
    "timestamp": "2026-06-21T15:20:10.020Z",
    "ext_version": "1.1",
    "ref_msg_id": "cere-20260621-152010-0001"
  },
  "body": {
    "status": "OK | PARTIAL_FAIL | GLOBAL_FAIL | TIMEOUT | REJECT | DEGRADE_LIMIT",
    "risk_level": "L0 | L1 | L2 | L3",
    "retry_count": 0,
    "lock_type": "",
    "wal_write": true,
    "sign_ecc05": "ec_sig_xxxxxx",
    "sign_mcc02": "mcc_sig_xxxxxx",
    "data": {},
    "fault": {
      "fault_code": "F1-404",
      "fault_category": "FILE",
      "severity": "MEDIUM",
      "message": "目标文件不存在"
    }
  }
}
```

### 2.4 回执状态枚举
- **OK**：全会话全部并行/串行任务执行完成且无故障。
- **PARTIAL_FAIL**：单分支子任务失败，其余分支正常完成（此时不上报OK）。
- **GLOBAL_FAIL**：会话全局熔断、不可恢复故障。
- **TIMEOUT**：任务报文超30s未入队自动丢弃。
- **REJECT**：安全校验不通过、签名缺失、负载超限、格式非法、L3高危拦截。
- **DEGRADE_LIMIT**：系统负载超限，并发限流拒绝任务。

## 三、核心操作报文定义
### 3.1 DAG任务下发请求（ECC→MCC-01）
```json
{
  "header": {
    "msg_type": "REQUEST",
    "source": "ECC-12",
    "target": "MCC-01"
  },
  "body": {
    "operation": "DAG_DISPATCH",
    "sign_ecc05": "ec_sig_xxxxxx",
    "risk_level": "L1",
    "user_confirm_timeout": 120,
    "dag": {
      "dag_id": "dag-session_x-001",
      "max_parallel": 6,
      "task_nodes": [
        {
          "task_id": "task_01",
          "deps": [],
          "op_type": "FILE_COPY",
          "params": {"src": "/a.md", "dst": "/out/"},
          "lock_type": "FILE",
          "risk_level": "L0"
        },
        {
          "task_id": "task_02",
          "deps": ["task_01"],
          "op_type": "CODE_RUN",
          "params": {"script": "main.py"},
          "lock_type": "NONE",
          "risk_level": "L1"
        }
      ]
    }
  }
}
```
**DAG下发接收ACK报文**
```json
{
  "header": {
    "msg_id": "cere-ack-xxxx",
    "msg_type": "NOTIFY",
    "source": "MCC-01",
    "target": "ECC-12",
    "session_id": "session_x",
    "timestamp": "2026-06-21T15:20:15.000Z",
    "ext_version": "1.1"
  },
  "body": {
    "operation": "DAG_ACK",
    "ref_msg_id": "cere-20260621-152010-0001"
  }
}
```
**DAG下发拒收通知报文**
```json
{
  "header": {
    "msg_id": "cere-rej-xxxx",
    "msg_type": "NOTIFY",
    "source": "MCC-01",
    "target": "ECC-12",
    "session_id": "session_x",
    "timestamp": "2026-06-21T15:20:16.000Z",
    "ext_version": "1.1"
  },
  "body": {
    "operation": "DAG_REJECT_NOTIFY",
    "ref_msg_id": "cere-20260621-152010-0001",
    "fault_code": "R2-01",
    "message": "单会话并行数量超限",
    "sign_ecc05": "ec_sig_xxxxxx",
    "sign_mcc02": "mcc_sig_xxxxxx"
  }
}
```

### 3.2 单分支/全会话执行回执（MCC-36→ECC-12）
```json
{
  "header": {
    "msg_type": "RESPONSE",
    "source": "MCC-36",
    "target": "ECC-12"
  },
  "body": {
    "operation": "TASK_FEEDBACK",
    "dag_id": "dag-session_x-001",
    "risk_level": "L1",
    "retry_count": 0,
    "wal_write": true,
    "sign_ecc05": "ec_sig_xxxxxx",
    "sign_mcc02": "mcc_sig_xxxxxx",
    "finished_task_count": 2,
    "failed_task_count": 0,
    "all_task_finished": true,
    "branch_details": [
      {
        "task_id": "task_01",
        "status": "SUCCESS",
        "exec_ms": 1200,
        "lock_type": "FILE"
      }
    ]
  }
}
```

### 3.3 全局/局部熔断通知（MCC-33→ECC-12）
```json
{
  "header": {
    "msg_type": "NOTIFY",
    "source": "MCC-33",
    "target": "ECC-12"
  },
  "body": {
    "operation": "FUSE_TRIGGER",
    "session_id": "session_x",
    "risk_level": "L2",
    "sign_ecc05": "ec_sig_xxxxxx",
    "sign_mcc02": "mcc_sig_xxxxxx",
    "fuse_scope": "BRANCH | SESSION",
    "trigger_reason": "UNRECOVERABLE_HARDWARE_ERROR",
    "affected_task_ids": ["task_02"],
    "auto_reset_after_sec": 300
  }
}
```

### 3.4 资源降级同步通知
**MCC主动上报（负载超限）：**
```json
{
  "header": {"msg_type": "NOTIFY", "source": "MCC-37", "target": "ECC-12"},
  "body": {
    "operation": "LOAD_DEGRADE",
    "cpu_usage": 86,
    "mem_usage": 93,
    "battery": 16,
    "allow_max_session": 4,
    "allow_single_parallel": 3
  }
}
```
**ECC主动下发（用户手动开启省电模式，永久覆盖自动硬件负载限制）：**
```json
{
  "header": {"msg_type": "NOTIFY", "source": "ECC-12", "target": "MCC-37"},
  "body": {
    "operation": "LOAD_DEGRADE",
    "trigger_source": "USER",
    "allow_max_session": 2,
    "allow_single_parallel": 1
  }
}
```

### 3.5 心跳卡死告警（MCC-37→ECC-12）
```json
{
  "header": {"msg_type": "NOTIFY", "source": "MCC-37", "target": "ECC-12"},
  "body": {
    "operation": "HEARTBEAT_STALL",
    "session_id": "session_x",
    "stall_task_id": "task_02",
    "stall_duration_ms": 10500
  }
}
```

### 3.6 会话断点恢复同步（MCC-04→ECC-12）
```json
{
  "header": {"msg_type": "NOTIFY", "source": "MCC-04", "target": "ECC-12"},
  "body": {
    "operation": "SESSION_RECOVER",
    "session_id": "session_x",
    "unfinished_dag_ids": ["dag-session_x-001"],
    "last_snapshot_time": "2026-06-21T15:18:00.000Z"
  }
}
```

### 3.7 跨设备会话同步通知（ECC-12→MCC-09）
```json
{
  "header": {"msg_type": "NOTIFY", "source": "ECC-12", "target": "MCC-09"},
  "body": {
    "operation": "SESSION_SWITCH",
    "session_id": "session_x",
    "target_device_id": "device_macbook_pro_02",
    "transfer_dag_ids": ["dag-session_x-001"],
    "sync_timestamp": "2026-06-21T15:25:00.000Z",
    "device_sign": "dev_sig_xxxxxx",
    "force_takeover": false
  }
}
```

## 四、全局故障错误码体系
- **F（文件类 F1~F7）**：路径校验、磁盘空间检查、提示用户更换路径。
- **A（应用类 A1~A6）**：检测软件安装状态、控件重定位重试。
- **N（网络类 N1~N6）**：自动重连、API指数退避重试最多3次。
- **C（命令脚本 C1~C5）**：拦截高危脚本、沙箱权限收紧。
- **B（剪贴板 B1~B3）**：等待互斥锁释放、自动脱敏重试。
- **R（并发资源 R1~R5）**：降低单会话并行数量、排队等待资源释放；R5-GLOBAL_FUSE为全局熔断标记，熔断后新任务直接返回DEGRADE_LIMIT。
- **H（硬件外设 H1~H3）**：提示设备连接、触发电量降级。

**细分故障码触发条件：**
- F1：文件不存在（路径无效） → 提示用户确认路径。
- F2：权限不足（访问拒绝） → 请求用户授权。
- F3：磁盘空间不足 → 清理临时文件或提示用户。
- F4：文件被锁定 → 等待锁释放后重试。
- F5：文件格式不匹配 → 转换格式或提示用户。
- F6：文件读写超时 → 重试或跳过。
- F7：文件完整性校验失败 → 重新下载或从备份恢复。
- A1：目标应用未安装 → 提示用户安装。
- A2：应用窗口无响应 → 等待或强制关闭后重试。
- A3：UI控件定位失败 → 调整定位策略或降级执行。
- A4：应用版本不兼容 → 提示更新应用。
- A5：应用内部弹窗阻塞 → 自动关闭弹窗或请求用户干预。
- A6：应用崩溃 → 重启应用并恢复上下文。
- N1：域名解析失败 → 切换DNS或提示用户检查网络。
- N2：连接超时 → 重试或切换备用接口。
- N3：HTTP 4xx客户端错误 → 检查请求参数。
- N4：HTTP 5xx服务端错误 → 指数退避重试。
- N5：SSL证书错误 → 提示用户安全风险。
- N6：网络带宽不足 → 降低并发请求数。
- C1：脚本语法错误 → 沙箱预检拦截。
- C2：高危系统调用 → 永久拦截。
- C3：脚本执行超时 → 终止并上报。
- C4：脚本注入风险 → 语义分析拦截。
- C5：脚本权限不足 → 沙箱降权执行。
- B1：剪贴板被占用 → 等待互斥锁。
- B2：剪贴板内容过大 → 分批传输。
- B3：剪贴板格式不支持 → 自动转换或提示用户。
- R1：全局并发会话数达上限 → 排队等待。
- R2：单会话并行任务数达上限 → 降低并行度。
- R3：文件/剪贴板/窗口/网络锁等待超时（10s） → 生成R3故障码，排队或提示用户。
- R4：网络端口耗尽 → 等待或复用连接。
- R5-GLOBAL_FUSE：全局熔断中 → 等待熔断解除或用户手动恢复，已有运行任务执行完毕后终止。
- V1-01：报文字段未知/类型不匹配 → 解析拒绝。

## 五、总线约束规则
### 5.1 安全强制约束
1. ECC 下发 DAG 任务 REQUEST 报文携带有效 sign_ecc05，MCC-02 校验通过即时生成 sign_mcc02 存入 DAG 上下文，双签名同步回填所有回执、熔断告警报文，校验不通过返回 REJECT。
2. 缺失任一签名直接返回 REJECT 状态回执，写入审计日志。
3. L3 永久拦截级任务在 ECC-12 网关预处理阶段直接拦截，不下发至总线。若报文异常流入总线，MCC-02 识别 L3 标记后丢弃并上报安全告警。
4. 所有回执、熔断类报文必须同步携带双签名用于日志归档校验。
5. 所有 operation=SESSION_SWITCH 跨设备同步NOTIFY报文必须携带 device_sign 设备配对签名；目标设备存在未解锁 session 只读锁时直接丢弃报文并生成拒收通知，仅局域网内同账户已绑定设备可通过校验。
6. 若拒收原因为锁未释放，ECC-12 判定原设备离线或卡死时，可下发携带 force_takeover: true 的二次接管报文。目标设备收到后必须强制释放本地只读锁、销毁本地 DAG 上下文，并立即向本地正在运行的所有相关 DAG 任务下发 HARD_KILL 信号；被 Kill 的任务严禁继续执行后续节点、严禁写入任何 WAL 日志，并立即向总线发送 GLOBAL_FAIL 回执。MCC完成批量终止后，主动推送FUSE_TRIGGER(BRANCH)通知携带全部终止task_id列表，ECC收到该熔断通知，确认本地会话销毁完成。

#### 签名生成规则
- 签名算法：HMAC-SHA256。
- 签名密钥：ECC-05 与 MCC-02 各自持有预共享对称密钥。
- 待签内容区分两类报文：
  1. 携带dag_id的DAG_DISPATCH：将header.msg_id、header.timestamp、header.session_id、body.operation、body.dag.dag_id分别Base64编码，以`.`固定顺序拼接；
  2. 其余无dag_id报文：header.msg_id、header.timestamp、header.session_id、body.operation分别Base64编码，以`.`拼接。
- 严禁将body.data及其内部字段纳入签名计算范围，确保载荷截断不影响签名校验完整性。
- 签名有效期：绑定 msg_id 与 session_id，时钟偏差仅日志告警，不判定签名失效。
- sign_ecc05由ECC-05生成嵌入REQUEST；sign_mcc02由MCC-02校验ECC签名后计算缓存，统一回填所有上行报文。

#### 报文防重放与校验顺序
1. 接收方校验顺序必须为：1.格式与版本校验 → 2.msg_id滑动窗口去重校验 → 3.时间戳防重放校验 → 4.签名密码学校验。任何一步失败立即返回REJECT并丢弃，严禁向后传递。
2. 接收方必须维护一个基于msg_id的滑动窗口去重队列，双淘汰策略：硬性上限最多缓存10000条msg_id或占用内存不超过2MB，达到上限采用LRU淘汰最旧记录；条目存放超过300s自动过期删除，释放内存，严禁无上限永久缓存报文标识。
3. 接收方校验header.timestamp，若与本地时间偏差超过±60s，直接返回REJECT并丢弃报文。

### 5.2 并发时序约束
1. 全局最大并发会话固定 8，单会话最大并行任务默认 6，负载上限取用户手动降级与硬件自动降级两者最小值，降级时同步下调。
2. 同session多条REQUEST串行排队处理，跨session报文分片并行解析。
3. 熔断、降级、锁相关NOTIFY报文优先级高于普通DAG任务，优先分发。
4. ECC下发DAG_DISPATCH REQUEST后，等待MCC-01返回DAG_ACK接收确认；2s未收到自动重传，最多重传3次，重传依靠msg_id幂等去重，不会重复生成DAG实例；3次失败记录总线通信告警。收到DAG_REJECT_NOTIFY直接终止当前DAG流程。
5. MCC-01接收DAG_DISPATCH报文后，MCC-05必须首先对task_nodes进行拓扑校验：有向无环图检测防循环、依赖引用完整性检测，所有deps数组task_id必须存在于当前task_nodes列表。任一检测失败，立即返回REJECT fault_code:R2-02 DAG_INVALID，严禁入队执行。
6. 存在SESSION_GLOBAL熔断标记时，该会话新接收DAG_REQUEST直接丢弃，统一返回GLOBAL_FAIL回执。
7. 仅当前全会话内全部串行、并行子任务执行完毕且无全局致命故障，MCC才上报OK完整回执；存在PARTIAL_FAIL分支仅返回PARTIAL_FAIL回执，不会触发MemoryBus解锁。ECC-12接收OK回执后经MemoryBus向MLNF-01下发解锁指令。
8. 任务执行失败自动累加retry_count，达到3次上限停止重试并上报故障。
9. ECC收到MCC任意RESPONSE报文后，回复携带ref_msg_id与timestamp极简ACK；MCC发出RESPONSE启动2s重传计时器，未收到ACK最多重传3次；3次无应答转为NOTIFY推送并写入本地WAL等待下次会话同步。

### 5.3 资源与限流约束
1. 报文体积与任务数量限制：所有REQUEST报文Payload上限2MB，超限直接丢弃并返回REJECT回执；单条DAG报文最多携带12个子任务。NOTIFY、RESPONSE无2MB硬性上限，但单条RESPONSE body不得超过500KB。
2. 总线单批次批量回执上限50条任务结果。
3. 任务报文生存周期30s，超时未处理自动丢弃并返回TIMEOUT回执。
4. 高危弹窗120s无用户确认，MCC自动拒绝当前DAG任务。
5. FILE/CLIPBOARD/WINDOW/NETWORK四类资源锁最大等待超时10s，超时生成R3故障码；单task占用多资源锁时lock_type使用英文逗号+空格分隔，格式`FILE, NETWORK`，用于抢占追溯。
6. 单task的risk_level优先级高于外层DAG总risk_level，安全校验时取层级最高值执行拦截判定。
7. WAL写入与截断策略：除强制写入项外，单条TASK_FEEDBACK回执若超过500KB，允许将data.trace等非关键日志字段置为`[TRUNCATED_DUE_TO_SIZE_LIMIT]`占位符，保留原字段键名维持双签名校验完整性，确保回执体积合规后发送。截断仅允许在总线报文组装阶段执行，MCC内存原始执行结果、WAL持久化记录保持完整，不可截断。

### 5.4 日志与幂等约束
1. WAL持久化规则：REQUEST、TASK_FEEDBACK执行报文wal_write标记可配置；FUSE_TRIGGER、SESSION_RECOVER、SESSION_SWITCH三类NOTIFY强制写入WAL；LOAD_DEGRADE、HEARTBEAT_STALL、DAG_ACK、DAG_REJECT_NOTIFY无需持久化。WAL本地记录留存7天，到期自动清理。
2. 依靠msg_id实现执行类报文幂等校验，重复接收相同msg_id直接丢弃不重复执行。
3. NOTIFY类报文按session_id+operation做状态去重，未变更重复消息自动合并丢弃，防止消息风暴。
4. 接收方解析报文发现未知必填字段或字段类型不符，返回REJECT CODE:V1-01，禁止填充默认值兼容。

### 5.5 单向NOTIFY报文重传与ACK规则
1. 熔断、降级、心跳、会话恢复等NOTIFY，ECC接收后回复极简ACK（携带ref_msg_id、timestamp）。
2. MCC未收到ACK则2s间隔重传，后续重传间隔翻倍（2s→4s→8s），最多重传3次；全部失败写入本地持久化日志，标记未确认事件，下次心跳/状态变更优先重放。
3. ACK风暴防御：MCC收到ECC极简ACK，若对应msg_id任务已清理，直接静默丢弃ACK，不触发重传与告警。

## 六、全局资源锁枚举（lock_type）
| 枚举值 | 说明 |
| ------ |------ |
| FILE | 文件读写互斥锁 |
| CLIPBOARD | 剪贴板操作互斥锁 |
| WINDOW | 窗口焦点与句柄操作互斥锁 |
| NETWORK | 网络请求与带宽占用互斥锁 |
| NONE | 无资源锁（只读或沙箱内操作） |

## 七、版本规范
1. 本规范CerebellumBus V1.1与MemoryBus V1.1协议版本对齐，整套EM-Core总线体系版本号统一。
2. 报文头部ext_version固定为"1.1"，主版本不一致直接丢弃，次版本向前兼容。
3. CerebellumBus与MemoryBus共用底层传输通道，业务报文隔离，支持联合升级。