# OpenSuperAgent

**在本地管理代码任务：明确授权、独立工作区、可检查的修改结果。**

[在线演示](https://xinyuchen-pku.github.io/OpenSuperAgent/) · [English](README.md) · [配置指南](docs/getting-started.md)

OpenSuperAgent 受到 DeepSeek SuperAgent 研究原型的启发，提供独立实现的任务运行框架与控制台。它把仓库请求转为持久化任务，通过模型和受限文件工具在独立 Git worktree 中执行，再展示任务摘要、代码差异和执行记录，由使用者检查与发布。

项目与 DeepSeek 没有隶属关系。当前版本为 v0.1 工程预览，功能范围与设计依据见[研究说明](docs/research.md)。

![OpenSuperAgent 控制台](docs/images/workspace.jpg)

## 已实现

- 本地创建、搜索和筛选任务，检查修改，补充上下文，停止与重试任务。
- SQLite 持久化授权依据、任务状态、执行次数、事件记录和 GitHub 读取位置。
- 每个任务独立 Git 工作区；兼容 OpenAI Chat Completions 格式，默认连接 DeepSeek。
- 支持读取、创建和修改文本文件，以及检查 Git 差异；每次文件操作限制为 64 KiB。
- GitHub webhook 校验签名、仓库、请求者名单和 agent 提及；重复事件保持幂等。
- 可选持续轮询 GitHub；带 `agent-candidate` 标签的事项只记录为候选，明确批准后开始执行。
- 重启后将中断任务标记为受阻，保留现有工作区；停止、重试和退出均不自动删除产物。
- GitHub Pages 公开演示使用浏览器本地示例数据，明确标记模拟执行，无需密钥。

## 本地启动

需要 Node.js 22+、pnpm 11、Python 3.9+、Git；支持 macOS 和 Linux。

```bash
git clone https://github.com/xinyuchen-pku/OpenSuperAgent.git
cd OpenSuperAgent
pnpm install --frozen-lockfile
pnpm build
python3 -m server.app
```

访问 **http://127.0.0.1:8765**。执行真实任务前，在启动服务的环境中配置：

```bash
export OSA_REPO=/你的仓库绝对路径
export OSA_BASE_URL=https://api.deepseek.com
export OSA_MODEL=deepseek-flash
# 通过环境安全设置 OSA_API_KEY，禁止提交到仓库。
python3 -m server.app
```

模型读取的仓库内容会发送给配置的模型服务。请选用可信仓库，并将密钥保存在仓库之外。Git worktree 共享 Git 元数据；文件访问检查提供工具权限边界，操作系统级隔离需要单独配置。

当前执行器没有命令行、测试执行、文件删除、提交、推送或合并工具。结果进入人工检查状态后，使用者运行仓库检查并自行发布。“标记已检查”只更新本地状态。当前也没有飞书、线程订阅、自动 PR 交付或分布式运行功能。

## 验证

```bash
python3 -m unittest discover -s tests -v
pnpm build
```

测试覆盖授权、并发派工、重启恢复、停止后响应、文件访问、签名事件以及真实 Git worktree 中的工具调用流程。协议测试使用脚本模型服务；真实商业模型的回答质量、账户额度和服务可用性由所选服务决定。

MIT License © 2026 Xinyu Chen。
