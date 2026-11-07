# 本轮模型服务配置

本轮使用 Qwen3-Coder-30B-A3B-Instruct、BF16、四张 A100-SXM4-80GB、vLLM 0.20.0。26 个模型与 tokenizer 文件的清单摘要为 `953dbd6e73944101fc6b15acde59399743f4e58031fba041072df8f0d7c123cc`，完整文件清单随原始证据提供。模型文件单独准备，交付包包含代码和身份记录。

以下命令用于已安装并验证 vLLM 0.20.0 的 GPU 环境。M2 按 `INSTALL-M2-source022.txt` 设置 `OSA_RESEARCH_DIR`；当前 source025 则将该变量设为本仓库 research 目录的绝对路径，并从安全位置预置 `VLLM_API_KEY`、`MODEL_DIR`；服务从环境加载凭据。为 `MODEL_CPU_SET` 选择机器允许的固定 32 个逻辑处理器位置，并保存实际选择。

```bash
python "$OSA_RESEARCH_DIR/osa_eval/vllm_length_priority.py" \
  --contract-check /absolute/path/to/vllm/entrypoints/openai/chat_completion/serving.py

export OSA_VLLM_COMPAT_RECEIPT="$PWD/model-compatibility.json"
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

CUDA_VISIBLE_DEVICES=0,1,2,3 \
taskset -c "$MODEL_CPU_SET" python "$OSA_RESEARCH_DIR/osa_eval/vllm_length_priority.py" \
  --model "$MODEL_DIR" \
  --served-model-name osa-qwen3-coder-30b \
  --host "${MODEL_BIND_ADDRESS:-127.0.0.1}" \
  --port "${MODEL_BIND_PORT:-8000}" \
  --dtype bfloat16 --tensor-parallel-size 4 \
  --max-model-len 262144 --max-num-seqs 4 \
  --max-num-batched-tokens 16384 --gpu-memory-utilization 0.90 \
  --enforce-eager --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --generation-config vllm --seed 20261102 --no-enable-prefix-caching \
  --override-generation-config '{"temperature":0.7,"top_p":0.8,"top_k":20,"repetition_penalty":1.05}'
```

启动器核对原始模块 SHA-256 `50b0eacd6acd4cfdaf1aa69a765be9c1bf1c3fac993cfdb95d9ef413a0be884e`，仅调整截断回复的结束原因优先级。其他服务版本按其实际结束原因和 tokenizer 接口验收，并保存版本身份。服务需支持 `/v1/chat/completions`、`/v1/models` 以及报告真实输入长度和上下文上限的 `/tokenize`。

框架客户端在 `prepared/config.json` 中填写服务地址、模型名和已核验身份，并通过 `LLM_API_KEY` 加载相应客户端凭据。使用内网 HTTP 地址时，设置 `model.allow_private_http=true`。三种子比较使用各自的请求种子 20261102、20261103、20261104；服务默认种子保持 20261102。

原始服务使用固定的 32 个宿主 CPU 执行位置，记录于 serving identity。当前命令中的网络绑定、模型目录、CUDA 库与 CPU 位置须按实际机器解析并记录。本轮驱动 535.261.03 配合任务私有 CUDA 13 兼容库运行，现有 GPU 环境经过真实请求验证；全新 GPU 宿主机的驱动安装不在本次干净 Python 安装验收范围。已有捕获补丁的原始 Harbor 重放可直接使用 `INSTALL-M2-source022.txt` 第 5 节命令。
