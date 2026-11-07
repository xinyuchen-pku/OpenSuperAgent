# 已捕获公开任务的官方重放

任务：`instance_internetarchive__openlibrary-09865f5fb549694d969f0a8e49b9d204ef1853ca-ve8c8d62a2b60610a3c4631f5f23ed866bada9818`。

补丁来自 source-022 的真实四任务 Eager 运行，原始官方得分为 1。此目录保留整批 identity/result/usage/accepted-summary 的原始字节，但只携带 OpenLibrary 的补丁和独立输出；模型成本字段仍属于原四任务批次。其他补丁和完整轨迹位于原始证据。

在 reproduction 目录，按 INSTALL.txt 安装原始 Harbor 和研究包，拉取 OpenLibrary 官方镜像后执行。单任务重放使用 CPU 0、1 CPU /4 GiB；不调用模型：

```bash
docker pull ghcr.io/scaleapi/swe-bench_pro-v2@sha256:1f57fc1a3fd6ee235fa5a2c9343faae47b3f2d422fe4709bbd2ba04309da158b
python official_regrade.py \
  --checkout "$PWD/upstream/SWE-bench_Pro-os" \
  --harbor "$PWD/.venv-harbor/bin/harbor" \
  --run ../public-example/captured-run --output captured-example-replay \
  --task-id instance_internetarchive__openlibrary-09865f5fb549694d969f0a8e49b9d204ef1853ca-ve8c8d62a2b60610a3c4631f5f23ed866bada9818 \
  --cpus '{"instance_internetarchive__openlibrary-09865f5fb549694d969f0a8e49b9d204ef1853ca-ve8c8d62a2b60610a3c4631f5f23ed866bada9818":0}'
```

每次选择新输出目录，保留原始结果。打包后的实际重放验收回执会另附；原始 CAPTURE-MANIFEST 的历史待验字段保留。

## 补充的单任务轨迹与成本

`worker-trajectory.jsonl.gz` 是同一原始成功运行中 OpenLibrary Worker 的完整相关行子集，保留原始行字节；`worker-cost.json` 保存调用 ID、原始轨迹摘要和成本拆分。该 Worker 实际调用24次，输入291,655 tokens、输出9,092 tokens，共300,747 tokens；共享 Router 与其他任务成本另计。原六份批次元数据仍属于四任务整体，未改写为单任务统计。轨迹与补丁保留 OpenLibrary 的原有许可，见第三方说明。

M3-A3 还在干净安装当前核心的环境中重新执行原始 Harbor，对该历史补丁得到得分1，并核对独立评分一致。这是零模型复现验收，不增加 source025 或当前模型的成功次数。
