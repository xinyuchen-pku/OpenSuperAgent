# 上游材料来源与许可

本项目作者编写的研究工具采用 MIT 许可，见研究模块与交付包的 LICENSE。评测材料中来自上游任务项目、Benchmark 和 SDK 的代码、测试、快照与补丁保留其原有许可；本项目的许可声明不重新授权这些上游材料。

`third-party-notices/` 保存四个 Pro 任务不可变镜像中读取的原始许可文本，以及原生 cachetools 最终仓库快照中的原始许可文本。PROVENANCE.json 和 NATIVE-PROVENANCE.json 给出来源、镜像或快照摘要、原文件路径和逐文件 SHA-256。许可提取仅创建停止状态的专用文件视图，未启动任务或调用模型；提取后只移除了经身份核对的专用临时容器。

Pro 任务分别来自 gravitational/teleport、qutebrowser/qutebrowser 和 internetarchive/openlibrary；原生任务来自 tkem/cachetools。任务和版本对应关系见任务矩阵、原始运行身份与源码清单。SWE-bench Pro、Harbor、AsynCodeBench、Software Agent SDK 及 DeepSeek 原型的固定来源见主报告和研究协议，原仓库保留各自的许可与署名。

模型权重、容器镜像、私有 TLS 凭据和 API 密钥不包含在交付包中。

## M3-A3 发布准备补充

`third-party-notices/upstream/` 保存实际固定提交中读取的 SWE-bench Pro、Harbor、AsynCodeBench、Software Agent SDK 与 DeepSeek 原型许可文本；PROVENANCE.json 记录逐文件摘要。mini-swe-agent 的实际许可与固定提交另存于同名目录。外部源码通过固定提交取得，未将修改后的标准 Agent 内核作为本项目实现发布。

作者研究内核及工具为 MIT。任务侧材料、模型补丁、代码片段和测试输出保留任务项目许可：Teleport（Apache-2.0）、qutebrowser（GPL-3.0）、OpenLibrary（AGPL-3.0）、cachetools（MIT）。这些材料的目录与来源清单用于区分许可范围。AsynCodeBench 原仓库为 Apache-2.0，其余上述固定工具仓库的原许可文本随附供核对。Qwen 模型权重不包含在源码发布中；使用时遵守其官方仓库声明的许可。

SWE-bench Pro 官方数据卡也明确区分 MIT 评测工具与保留原项目许可的任务内容，见 [官方 License 声明](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro#license)（2026-11-07核对）。
