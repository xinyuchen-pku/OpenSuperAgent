<p align="center">
  <img src="docs/images/opensuperagent-logo-tile.png" alt="OpenSuperAgent 标志" width="96" height="96">
</p>
<h1 align="center">OpenSuperAgent</h1>
<p align="center"><strong>AI 编码 Agent 协作系统的可复现实验。</strong></p>
<p align="center">
  <a href="README.md">English</a> · 简体中文 ·
  <a href="research/reproduction/INSTALL.txt">复现结果</a> ·
  <a href="research/START-HERE.md">研究总览</a>
</p>

OpenSuperAgent 研究持续在线、能够处理后续事件的编码 Agent 能否带来额外收益。我们使用共同的编码内核比较五种调度方案，公开 Benchmark 评分、执行轨迹与 tokens 账本。

## Benchmark 结果

点击图表可查看完整矢量图。

[![五架构 Benchmark Pilot：成功率、平均批次耗时和实际 API tokens](docs/results/benchmark-pilot.png)](docs/results/benchmark-pilot.svg)

**本轮 Pilot 尚未建立 Super-agent 的优势。** Eager Delegation、Single + Subagent 各成功 3/12，Super-agent 成功 2/12。实验使用 Qwen3-Coder-30B-A3B-Instruct 和冻结 source022，包含 **4 道独立题目 × 3 个配对种子**。成功案例全部来自 OpenLibrary，结果为描述性小样本比较。

[完整报告与评分证据](research/M2-REPORT-003.md) · [图表数据与统计口径](docs/results/README.md)

## 模型能力

[![Qwen30B、Next 与共同 Worker，以及 Next 与 mini-swe-agent 的必需测试通过情况](docs/results/model-capability.png)](docs/results/model-capability.svg)

同一共同 Worker 下，Qwen3-Coder-Next 成功 **1/3 题**，Qwen30B 为 **0/3**。Next + mini-swe-agent 同样为 0/3，但在 qutebrowser 上通过了更多测试。这组 **3 题、1 个种子**的结果支持下一步模型选择，模型与框架的更广泛比较仍需扩大任务覆盖。

[M3-A3 结果、轨迹与预算](research/studies/m3-a3/README.md)

## 系统测量

[![确定性系统测量：16 任务批次耗时，以及后续事件下的 Router 预设回复次数](docs/results/system-mechanisms.png)](docs/results/system-mechanisms.svg)

16 任务、4 槽位下，Eager Delegation 耗时 **0.540 秒**，Super-agent 为 **0.542 秒**。36 个事件的工作负载中，订阅将 Router 预设回复次数从 **36 降为 4**。这组测量使用确定性 Worker、三次重复，**真实模型 API 调用为零**；真实编码结果见上方实验。

[System Track 报告](research/studies/m3-a3/SYSTEM-REPORT.md) · [原始数据与绘图脚本](docs/results/README.md)

## 复现与文档

- **开始使用：**[安装与无密钥系统检查](research/reproduction/INSTALL.txt)。
- **复现实验：**[历史五架构 Benchmark](research/reproduction/INSTALL-M2-source022.txt) · [当前 Worker 与补丁重放](research/reproduction/RUN-CAPABILITY.md) · [原生 Benchmark 指南](research/NATIVE-RUNBOOK.md)。
- **阅读方法：**[研究范围](research/START-HERE.md) · [架构比较协议](research/PROTOCOL.md) · [图表数据与重新生成](docs/results/README.md)。

**当前进度：**Worker 校准已结束，后续扩大比较采用 Next + source025。首轮 M3-B1 因模型请求超时触发用量未确认的停止条件，完整的新五架构对照尚未发布。[后续实验方案](research/studies/m3-b1/README.md)。

当前为研究预览版，提供受 [DeepSeek 公开原型](https://github.com/deepseek-ai/dsh-superagent-prototype)启发的独立任务级实现，与 DeepSeek 没有隶属关系。完整 DSH 宿主、完整 Watchdog 行为和任务内递归委派仍需集成，范围详见研究文档。此前的[网页工作台](docs/getting-started.md)使用独立执行器。

[MIT 许可](LICENSE) · [第三方声明](research/reproduction/THIRD-PARTY-NOTICES.md) · [参与贡献](CONTRIBUTING.md) · [Logo](docs/BRANDING.md)
