"""Read the original native integrated dependency selectors from an unchanged test report."""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser();p.add_argument('test_report',type=Path);p.add_argument('native_metrics',type=Path);a=p.parse_args()
report=json.loads(a.test_report.read_text());spec=json.loads(a.native_metrics.read_text());outcomes={x['nodeid']:x['outcome']for x in report['tests']}
rows=[]
for i,dependency in enumerate(spec['dependency_points']):
 tests=dependency['integrated_probe_tests'];assert tests and all(t in outcomes for t in tests),'Incomplete native test report'
 rows.append({'index':i,'passed':all(outcomes[t]=='passed'for t in tests),'tests':tests})
print(json.dumps({'tests_passed':report['summary']['passed'],'tests_total':report['summary']['total'],'integrated_dependencies_passed':sum(x['passed']for x in rows),'total_dependencies':len(rows),'dependencies':rows,'model_calls':0,'scope':'Native final integrated assertions; no rerun of two-worker protocol'},indent=2))
