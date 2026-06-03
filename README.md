# Agent-ecc-brain：AI Agent 认知大脑

**EM-Core 认知中枢 · AI Agent 专项实现**

> 版本：V1.0
> 原创提出者：文波福
> 开源协议：CC BY-NC 4.0（署名-非商业性使用 4.0 国际许可证）
> 所属体系：EM-Core Agent 通用智能系统
> 配套仓库：[EM-Core-Agent-Spec](https://github.com/expanding-research/em-core-agent-spec)（总规范）｜ [Agent-mlnf-mem](https://github.com/expanding-research/agent-mlnf-mem)（记忆中枢）｜ [Agent-mcc-exec](https://github.com/expanding-research/agent-mcc-exec)（行动执行层）


## 一、仓库定位

本仓库是 EM-Core Agent 的 **认知大脑**，负责意图解析、任务规划、工具选择、安全仲裁等核心推理功能。只输出高层决策指令，不直接执行具体工具调用。


## 二、核心模块

| 模块编号 | 模块名称 | 核心职责 |
|:---:|------|------|
| ECC-01 | 意图解析模块 | 将用户自然语言输入转化为结构化意图 |
| ECC-02 | 任务规划模块 | 拆解复杂任务为可执行步骤序列 |
| ECC-03 | 工具选择模块 | 根据任务需求匹配最合适的工具 |
| ECC-04 | 安全仲裁模块 | 审查工具调用方案，执行安全边界检查 |
| ... | ... | ... |

完整模块定义及接口规格见 [spec/](./spec/) 目录。


## 三、与记忆中枢及行动执行层的协同

- 从 [Agent-mlnf-mem](https://github.com/expanding-research/agent-mlnf-mem) 查询用户偏好与历史经验
- 向 [Agent-mcc-exec](https://github.com/expanding-research/agent-mcc-exec) 下发工具调用指令并接收执行反馈


## 四、开源协议与商业授权

基础版采用 **CC BY-NC 4.0** 协议开源。商业使用需获得 [商业授权](../LICENSE-COMMERCIAL.md)。


## 五、联系方式

- **原创提出者**：文波福
- **邮箱**：710705008@qq.com