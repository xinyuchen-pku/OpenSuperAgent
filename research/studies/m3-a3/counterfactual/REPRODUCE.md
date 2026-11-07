# 两类最小修复的零模型诊断

原实验使用完整 source025 模型产物（Git 完整合入重放后172/215），没有重新调用模型。公开 base-code.tar.gz 保留全部非 Git 文件字节，原完整产物及公开代码副本摘要见 BASE_CODE_PROVENANCE.json。

实际环境：Python3.10.12、pytest9.0.3、pytest-json-report1.5.0；容器1CPU、4GiB、禁网。执行镜像标识与环境回执随实验材料提供。各个条件分别从同一原始代码副本开始，依次应用 A_arguments_only、B_wrapper_metadata_only 或 AB_both 目录中的补丁；原始条件保持原样。

```bash
python3.10 -m venv .venv-cf
.venv-cf/bin/python -m pip install pytest==9.0.3 pytest-json-report==1.5.0
CF_PYTHON="$PWD/.venv-cf/bin/python"
tar xf base-code.tar.gz
cd cachetools_repo
git apply ../AB_both/replay.patch
PYTHONPATH=src:. "$CF_PYTHON" -m pytest -q -p no:cacheprovider -o addopts= --json-report --json-report-file=report.json tests
"$CF_PYTHON" ../score_dependencies.py report.json ../ORIGINAL_METRICS_SNAPSHOT.json
```

原215项测试和原五项 integrated_probe_tests 均保持原字节/定义。五组选择器来自 ORIGINAL_METRICS_SNAPSHOT.json，与实际原生 final_integrated 检查点逐项核对一致。依赖通过要求该依赖列出的所有集成测试通过。

| 条件 | 测试通过 | 集成依赖通过 |
| --- | --- | --- |
| 原模型完整代码 |172/215|0/5|
| 只修复 methodkey/typedmethodkey 真实参数 |179/215|1/5|
| 只将元数据绑定到配置式装饰器的最终包装函数 |196/215|3/5|
| 两类修复合并 |203/215|4/5|

余下12项分别涉及六种装饰器的 maxsize=None 元数据和直接使用装饰器的调用形式。此诊断保持这些模型逻辑原样，没有扩展修复。依赖指标依据原生登记的最终集成断言计算；双 Worker async_private 编排没有在本反事实中重新执行。以上均为零模型诊断，不增加模型成功次数，也不定义模型依赖解决步数。

`replay.patch` 为可直接应用的分发补丁，结果文件摘要与实际评分产物一致；原始 `cf243.patch` 文本投影保留供审计。
