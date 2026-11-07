# 重新生成分析结果

在交付包或仓库的研究模块根目录运行以下命令。`analysis/` 保存分析程序，`data/` 保存已核验的派生数据，`reproduction/` 保存冻结配置。原始逐例材料位于证据归档。

图表实际使用 Python 3.12.7 与 Matplotlib 3.9.2；其余分析脚本只依赖 Python 标准库。安装图表依赖后，使用新目录重新生成，保留已交付文件：

```bash
python -m pip install matplotlib==3.9.2
python analysis/plot_results.py --summary data/comparison-summary.json --output figures-recomputed
python analysis/write_analysis_tables.py --summary data/comparison-summary.json --output tables-recomputed
```

图表程序要求完整的 60 份主评分和 20 份有效参照，采用真实 API tokens 与会话锁时间。`--first-block-only` 仅用于已标识的历史阶段进展图。最终交付采用完整数据。

`analyze_native.py` 从原生 JSON、两份 Worker 用量账本、控制回执和实际 SDK 容器资源证明生成原生指标；它不打开已完成的 SQLite 数据库。运行时提供 `--run`、`--controller-receipt`、`--resource-proof`、`--workspace-proof` 与位于不可变运行目录之外的 `--output`。证据归档中相应目录分别为 `native-local-final/`、`native-resource-proof078/` 和 `native-host-transport-004/`。

最终 Markdown 可用以下命令重新生成。报告生成时间与累计经过时间会更新，实验结果保持由输入数据决定：

```bash
python analysis/build_report.py --summary data/comparison-summary.json --native data/native-summary.json --public data/public-acceptance.json --cost data/cost-ledger.json --uniform-scoring data/uniform-scoring-recheck.json --output report-recomputed.md
```

API tokens 的分项说明与全部服务实例的总成本已分别保存，分项属于总额的子集，重新汇总时按成本台账中的互斥服务实例计数。原生协议、独立任务调度架构和公开任务验收的统计范围分别记录。
