# 原生任务的运行条件

原生 AsynCodeBench 沿用固定版本的任务分解、私有工作区、权限、100-response profile 与评分。本轮验收为 `asyncodebench:cachetools` / `async_private`，研究 Adapter 的选择路径是 `osa_eval.asyncodebench_adapter:SharedWorkerAdapter`。五种研究架构与 Benchmark 的协议名称分别记录。

冻结研究源码中的 `NATIVE-RUNBOOK.md` 给出原始环境安装和运行命令。当前 M2 的模型参数、源代码身份和实际验收结果，以最终报告及原始运行目录为准；该文件内的早期实验描述作为历史背景保留。

实际原生执行使用与 Pro 相同的本机 Linux VM 总池：4 vCPU、16 GiB，无 guest swap。原始 SDK 的单容器资源配置保持原样；实际 cgroup 值随原生资源证明提供。Pro 每任务 1 CPU / 4 GiB 的验收条件单独报告。

SDK 的 source-minimal 镜像建立在固定的原始 `wentingzhao/cachetools` 任务镜像上，SDK Dockerfile 保持原样。为了在本机离线执行，另外准备了锁定的 Python 依赖，以及只包含初始提交的任务仓库缓存。准备过程、依赖清单、镜像摘要和构建文件位于原始证据的 `native-runtime-recipe071/`。容器磁盘、镜像层、模型权重和私有连接凭据均不随交付包分发。

研究 Adapter 在控制主机从冻结 source-022 加载；准备镜像用于 SDK 服务与任务执行。实际选择的模块路径和字节摘要独立记录。控制主机通过专属加密连接访问本机 Docker；SDK 回调使用字节流转发，原始 SDK 和任务协议保持不变，转发过程不记录请求内容或凭据。

本轮验证范围是准备完成的运行环境中的原生任务执行与官方 bundle 验证。完整新宿主机重建这一原生环境仍是明确的复现缺口。公开 Pro 任务的干净 Python 环境安装、真实模型重新生成和捕获补丁重放另行验收，详见 `INSTALL.txt` 与最终报告。
