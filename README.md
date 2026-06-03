# Agent-mcc-exec：AI Agent 行动执行层

**EM-Core 执行中枢 · AI Agent 专项实现**

> 版本：V1.0
> 原创提出者：文波福
> 开源协议：CC BY-NC 4.0（署名-非商业性使用 4.0 国际许可证）
> 所属体系：EM-Core Agent 通用智能系统
> 配套仓库：[EM-Core-Agent-Spec](https://github.com/expanding-research/em-core-agent-spec)（总规范）｜ [Agent-ecc-brain](https://github.com/expanding-research/agent-ecc-brain)（认知大脑）｜ [Agent-mlnf-mem](https://github.com/expanding-research/agent-mlnf-mem)（记忆中枢）


## 一、仓库定位

本仓库是 EM-Core Agent 的 **行动执行层（MCC）**，负责接收认知大脑下发的工具调用指令，执行具体的 API 调用、代码运行、文件操作等，并返回结构化执行结果。只负责精准执行，不参与任务决策。


## 二、核心模块

| 模块编号 | 模块名称 | 核心职责 |
|:---:|------|------|
| EXEC-01 | 工具注册中心 | 管理可用工具目录及其参数约束 |
| EXEC-02 | API 调用引擎 | 安全地执行外部 API 请求 |
| EXEC-03 | 代码执行沙箱 | 在隔离环境中运行用户或系统生成的代码 |
| EXEC-04 | 结果校验器 | 验证执行结果是否符合预期 |
| ... | ... | ... |

完整模块定义及接口规格见 [spec/](./spec/) 目录。


## 三、与认知大脑的协同

- 接收 [Agent-ecc-brain](https://github.com/expanding-research/agent-ecc-brain) 下发的工具调用指令
- 返回结构化执行结果及偏差报告


## 四、开源协议与商业授权

基础版采用 **CC BY-NC 4.0** 协议开源。商业使用需获得 [商业授权](../LICENSE-COMMERCIAL.md)。


## 五、联系方式

- **原创提出者**：文波福
- **邮箱**：710705008@qq.com