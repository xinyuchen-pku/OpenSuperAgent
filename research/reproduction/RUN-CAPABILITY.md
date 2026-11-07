# 单题能力对照的可移植入口

本入口复用 source025 与本轮同一标准 Agent 适配。任务、预算与比较范围见 ../studies/m3-a3/METHODS.md。完整实验结果由当时冻结的执行脚本生成；此可移植入口已经通过零模型准备验收，付费生成后的逐字轨迹可能不同。

以下从仓库根目录执行，需要 Linux、Git、Docker、uv 和真实生效的每任务1CPU/4GiB限制。先按 INSTALL-M2-source022.txt 的原始输入准备、镜像获取及正负对照步骤建立固定 checkout、Harbor 和 gates；在独立M2环境执行该准备，不覆盖当前研究内核。原始Harbor的锁定依赖通过独立环境保留。

```bash
python3.12 -m venv .venv-capability
.venv-capability/bin/python -m pip install --no-deps ./research
git -c core.autocrlf=false clone https://github.com/SWE-agent/mini-swe-agent research/reproduction/upstream/mini-swe-agent
git -C research/reproduction/upstream/mini-swe-agent checkout --detach 04d809ceab9df28f9adaed044884180159172930
.venv-capability/bin/python -m pip install ./research/reproduction/upstream/mini-swe-agent
cp research/reproduction/capability.template.json research/reproduction/capability.local.json
```

在 capability.local.json 填写模型接口、服务名称和完整身份。top_p、top_k、repetition_penalty及prefix cache由服务端固定为登记值；请求配置保留温度、最大输出与种子。接口须提供 /tokenize 和真实max_model_len，先核验截断回复的finish_reason。密钥由主机环境 LLM_API_KEY 加载，运行时不会复制给任务容器。实际服务是私有HTTP时，需要显式设置allow_private_http=true并保留网络访问边界。

```bash
TASK_ID="$(.venv-capability/bin/python -c "import json; print(json.load(open('research/reproduction/capability.local.json'))['tasks_in_fixed_order'][0])")"
.venv-capability/bin/python research/reproduction/run_capability.py \
  --config research/reproduction/capability.local.json \
  --checkout research/reproduction/upstream/SWE-bench_Pro-os \
  --gates research/reproduction/gates/evaluator-gates.json \
  --harbor research/reproduction/.venv-harbor/bin/harbor \
  --task-id "$TASK_ID" --cpu-index 0 --agent source025 \
  --output results/capability-preflight-001 --prepare-only
```

准备成功后，选择新的输出目录，删除 --prepare-only 即执行真实模型。另一个条件将 --agent 改为 mini，并添加 --mini-checkout research/reproduction/upstream/mini-swe-agent；重复三道预登记任务。每个条件使用同一不可变镜像、相同工具能力与预算，同一执行位置不得叠加其他正在运行的任务。

每题最多2M实际API tokens、100次调用、单条工具120s、执行3600s、最大输出8192；原始评分的时限单独遵循任务定义。结果保存原补丁、SQLite、模型与工具轨迹、实际用量、独立评分、原始Harbor输出及协议验收。标准Agent的提示、工具格式、观察截断与显式提交保留原样，属于执行方式变量。prepare-only核对输入、安装模块与上游身份，真实运行另行核对资源/禁网/隐藏材料边界。

远程Docker可通过 --docker-prefix 指定JSON客户端前缀，端点及TLS凭据由主机环境提供。活动SQLite目录应位于控制主机本地文件系统，完成后再做持久归档和逐文件摘要核验。原生AsynCodeBench沿用原协议，不通过此Pro入口执行。


## 仅重放本轮source025成功补丁

以下读取已捕获补丁，新增模型调用为0。独立环境只安装当前研究包；Harbor仍使用其单独的固定依赖环境。任务、镜像与资源须按前述说明准备。

```bash
mkdir extracted-m3-a3
tar xf research/studies/m3-a3/evidence/final-capability377.tar.gz -C extracted-m3-a3
TASK_ID="$(.venv-research/bin/python -c "import json; print(json.load(open('research/reproduction/capability.template.json'))['tasks_in_fixed_order'][2])")"
.venv-research/bin/python research/reproduction/official_regrade.py \
  --checkout research/reproduction/upstream/SWE-bench_Pro-os \
  --harbor research/reproduction/.venv-harbor/bin/harbor \
  --run extracted-m3-a3/capability/next-source025-recovery335/task003 \
  --output results/source025-captured-replay-001 --task-id "$TASK_ID" \
  --cpus "{\"$TASK_ID\":0}"
```

可将CPU0替换为宿主机允许的其他空闲执行位置；每个评分实例仍为1CPU/4GiB。该成功补丁在只安装opensuperagent-eval0.1.4的干净环境中已重放为1，原始/独立结果一致，安装模块摘要与source025一致，见当前研究的CURRENT_SOURCE025_CLEAN_REPLAY394.json及clean-replay394归档。历史source022成功案例保持独立身份。
