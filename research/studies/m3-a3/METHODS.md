# M3-A3：Worker Capability Boundary — 实际协议

目标是区分模型配置与 Agent 执行方式的表现，并让系统机制测试独立于编码成功率推进。本轮没有修改 source025 的 Prompt 或执行内核，没有训练模型，也没有启动 M3-B 的24题扩展。

## 能力对照

按 M2 冻结前四题中每个不同仓库的首次出现顺序，选择 Teleport、qutebrowser、OpenLibrary 三题。已有结果在选题前已知；任务、模型、标准 Agent、预算和停止条件均在新模型调用前登记，见 CAPABILITY_PREDECLARATION.json。

| 条件 | 模型 | 执行方式 |
| --- | --- | --- |
| 当前基线 | Qwen3-Coder-30B-A3B-Instruct | source025 |
| 模型对照 | Qwen3-Coder-Next，固定HF提交 a7fbcb5c0e12d62a448eaa0e260346bf5dcc0feb | 相同 source025 |
| 执行方式对照 | 同一 Qwen3-Coder-Next | mini-swe-agent 的固定上游 DefaultAgent、官方 mini.yaml、工具解析与观察格式；共同的模型记账和 Docker 适配 |

mini-swe-agent 固定提交为04d809ceab9df28f9adaed044884180159172930（2.4.6）。上游 Agent 核心与 Prompt 没有修改。共同适配替换模型传输与环境，保留标准 Agent 的显式提交、格式错误处理和线性历史；其提示、观察截断和结束规则属于执行方式这个变量，结果同时覆盖这些差异。

source025条件使用Kernel.work直接Worker入口；额外完成声明检查关闭，该配置在首次付费请求前登记。标准Agent保留原始完成规则。此项对照评估该固定Worker配置，M3-A2原生范围约束按其独立协议保留。

每题限制：实际1CPU、4GiB、2M实际API tokens上限、最多100次模型调用、单条工具120s、任务执行3600s；模型上下文262144、最大输出8192。三个条件使用temperature0.7、top_p0.8、top_k20、repetition_penalty1.05、seed20261102、prefix cache关闭、BF16及4卡张量并行。模型服务为同一vLLM0.20及固定长度处理兼容补丁。

工具能力均为任务容器内Bash执行。原始指令、镜像、测试、隐藏材料隔离和CPU/RAM契约沿用固定的官方输入。每个最终补丁交给新容器中的独立评分及原始Harbor，两者测试结果逐项核对。原始结果对象的自建后端协议标志保留，正式评分有效性由独立的 protocol-attestation.json 记录。

基线三题同时提供；更大模型与标准Agent分组顺序运行。在线batching与浮点计算会使同一种子产生不同轨迹。三题、一个种子只提供组合配置的描述性结果；模型、Prompt、交互格式与结束规则的完整交互作用仍需更多独立任务验证。

## 基础设施故障与恢复

第一次Next服务中，Teleport与OpenLibrary的工具写入及补丁保存超时，模型用量完整保留；它们从能力对照中排除，消耗2,053,514tokens单列为故障开销。有效的qutebrowser失败保留原样。

故障原命令分别在新工作区零模型重放，约0.24s及0.22s正常返回；短命令、10k、50k写入验证也通过。原故障触发原因未完全确认。恢复增加进程范围的Windows保活措施，原系统电源设置保持原样；原权重改为预加载，推理参数、权重字节、任务和Worker不变。只重试两次无效运行一次，之后运行原定标准Agent组；再次发生执行通路故障则停止。登记见RECOVERY_PREDECLARATION.json。

有效9项试验上限仍为18.02M tokens，故障2.05M单列，总上限约20.07M；全部模型服务的GPU驻留上限仍为14GPU·小时。硬件价格未知，USD成本未估；Mini内部的零美元计数只是自托管API占位，实际tokens与GPU驻留分别报告。

## System Track

source025 的真实 Runtime、Kernel 和 Journal，配合固定路由决策、5ms Worker回复、10ms路由回复与每事件100ms异步等待。每个接收事件对应一个不同工作单元，核对全部完成，避免不同合并时序改变总工作量。

负载1/4/8/16、Worker槽位1/4、五种架构，每格三次重复，共120格；三种Router条件、0/1/8个后续事件、每格三次，共27格。另测独立进程重启后的空闲检查点恢复与不确定工具操作拒绝重放。运行主机、Python与存储见SYSTEM_ENVIRONMENT.json。

槽位是逻辑并发容量；固定等待工作负载没有测量真实编译的CPU吞吐。Router返回固定委派决策，Single+Subagent在该负载中也选择委派。全部API调用和API tokens均为0；上下文字符数单列，不换算成真实模型推理费用。

## 复现入口

- 零模型系统：`python research/reproduction/system_track.py results/system-001`。
- 能力运行：在独立环境安装source025，准备固定原始输入和资源门槛；以reproduction/capability.template.json配置模型。运行 `run_capability.py --agent source025` 或 `--agent mini --mini-checkout ...`，先使用 `--prepare-only` 核对身份。
- 标准Agent：从其官方仓库克隆并检出上述固定提交，安装原依赖；保留官方mini.yaml。
- 反事实：见counterfactual/REPRODUCE.md，原生最终测试与五项集成依赖断言；零模型诊断不增加模型成功次数。
- 已捕获公开任务：见../../public-example，完整Worker轨迹、独立成本、原补丁和原始Harbor重放。

开源安装与来源许可见../../START-HERE.md及../../reproduction/INSTALL.txt。M2成绩保留source022；当前核心为source025/0.1.4。完整DSH宿主环境及任务内部递归分解仍是明确缺口。
