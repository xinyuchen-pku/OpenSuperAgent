# Stage 1：开源复现与研究评测

当前研究内核为 **source025 / 0.1.4**。五组比较的是任务级调度：Single、Single + Subagent、Eager Delegation、Router–Worker、Super-agent。研究内核独立于仓库原有的网页工作区。

这是任务级Super-agent研究版本，执行内核采用公开核心适配与受控实现；完整DeepSeek DSH宿主的逐字节复现尚未实现。现有数据提供了可运行性、原生评分和故障诊断证据；Super-agent 的真实任务收益仍在评估。

| 路线 | 已有证据 | 结果边界 |
| --- | --- | --- |
| System Track | 冻结执行内核、确定性工作负载、事件重放、进程恢复、订阅对照 | 只报告系统机制与测量延迟；模型 API 调用为零 |
| Capability Track | SWE-bench Pro 原始 Harbor 评分；原生 AsynCodeBench 协议；真实模型调用与成本记录 | 能力结果仍为小规模Pilot；M3-B1按原24题清单启动独立任务确认 |

从 [安装说明](reproduction/INSTALL.txt) 开始。最低成本入口是零模型 System Track；公开任务和五组脚本使用独立环境和预先声明的预算。

## 版本与历史结果

- [M2 报告](M2-REPORT-003.md)：source022 的四任务、三个种子、五种架构比较。
- [M3-A2 报告](studies/m3-a2/M3-A2-报告.md)：source025 的角色范围约束与语义失败诊断。172/215 是原模型产物的零模型完整合入重放。
- [M3-A3 材料](studies/m3-a3/README.md)：最小反事实修复、模型与标准 Agent 对照、独立系统测量。
- source022 的原始内核、安装 wheel 和清单保存在 frozen/source022；当前包保留 source025 的文件摘要，历史数据维持原版本身份。

## 已实现范围与缺口

| 能力 | 实际范围 |
| --- | --- |
| 五组架构公平控制 | 同一个 Worker、工具和资源上限；任务级调度 |
| 原始 DeepSeek 核心 | 固定提交的原始 Engine、仓储与任务生命周期适配；原始核心测试证据见 M2 |
| 完整 DSH 宿主环境 | 尚未集成 |
| Watchdog | 已有任务/工具时限与不确定操作拒绝重放；完整DSH监督、自动重派与恢复尚未覆盖 |
| 任务内部递归分解与集成 | 尚未实现 |
| 持久 Router 与 Subscription | 有确定性机制测试及有限真实模型小样例；复杂任务收益待评估 |
| 恢复 | 已确认空闲检查点后的跨进程恢复；不确定外部操作需要明确核对 |
| 原生角色边界 | 只读执行环境、受限编辑接口与可信交付；还需实际 SDK 控制入口隔离 |
| 编码能力 | 部分任务成功，仍存在语义与收尾失败；没有为某一种架构单独调整 Worker |

上游许可与署名见 [第三方说明](reproduction/THIRD-PARTY-NOTICES.md)。模型权重、容器镜像、凭据和原始上游完整仓库不随源码发布。

## 轨迹与版本读取

冻结源码的旧扁平 `trace.jsonl` 中，事件载荷自身的 `kind` 会覆盖记录类型。事件测量以 SQLite 日志为准；`reproduction/export_trace.py` 为已经完成并校验的日志生成“记录字段＋独立载荷”视图，保留原文件字节。其验收覆盖36个接收事件、其中32个后续事件。当前包的安装元数据为0.1.4，模块内旧版本常量仍为0.1.0；实验身份采用 SOURCE_MANIFEST 与实际模块摘要。

SOURCE_MANIFEST中的未提交状态记录实验冻结时的原始身份；当前发行状态以仓库提交、标签及Release为准。同一文件摘要继续定位原冻结内核。

最新阶段决策见 [M3-B1预登记](studies/m3-b1/README.md)：Worker Calibration已结束，使用冻结Next + source025；历史报告保留各自里程碑时点。系统固定工作量测量与真实模型端到端成功率分别报告。
