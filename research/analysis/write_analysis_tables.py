"""Export complete case-level costs, latency and failure evidence from JSON."""
from pathlib import Path
import argparse,csv,json

def main():
 p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=json.loads(a.summary.read_text(encoding='utf-8'));assert d['accepted_primary_grades']==60 and d['accepted_secondary_grades']==20 and len(d['cases'])==80;a.output.mkdir(parents=True,exist_ok=False)
 def csvfile(name,rows):
  keys=list(dict.fromkeys(k for row in rows for k in row))
  with(a.output/name).open('w',encoding='utf-8-sig',newline='')as f:
   w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
   for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(dict,list))else v for k,v in row.items()})
 csvfile('cases.csv',d['cases']);csvfile('batches.csv',d['batches'])
 lines=['# 逐例任务结果与失败证据','','本表来自完整 60 份主评分和 20 份单任务参考。Worker tokens 仅分配给真实会话执行区间中的工作请求，协调开销单独记在批次表中。模型声明完成与官方成功分别列示。','','| 范围 | 架构 | 种子 | 任务 | 官方成功 | 模型状态 | 提交延迟秒 | Worker tokens | 失败证据 |','|---|---|---|---|---|---|---:|---:|---|']
 for row in d['cases']:
  tid=row['task_id'];label=('Teleport-1'if'59d39dee'in tid else'Teleport-2'if'10123c'in tid else'qutebrowser'if'qutebrowser'in tid else'OpenLibrary');reason=row.get('collection_failure')or''
  if not row['success']and not reason:
   failed=row.get('required_nonpassing_tests')or[];reason='; '.join(x['name']for x in failed)or'官方必需测试未全部通过；详情见 cases.csv 和原始输出'
  if row['agent_state']=='blocked':reason+='; '+str(row.get('agent_claim')or'')[:220]
  if row.get('compilation_diagnostics'):reason+='; '+'; '.join(row['compilation_diagnostics'])[:500]
  reason=reason.replace('|','/').replace('\n',' ');lines.append(f"| {row['section']} | {row['architecture']} | {row['seed']} | {label} | {row['success']} | {row['agent_state']} | {row['latency_s']:.2f} | {row['worker_actual_api_tokens']:,} | {reason or '通过'} |")
 lines+=['','完整任务 ID、补丁 SHA-256、模型声明、编译诊断、必需测试状态与缺失测试、原始目录位于 cases.csv。超时没有最终测试输出时，收集测试数和测试状态保持未知。协调调用及成本、预留总量、拒绝数、真实重叠和输入上限位于 batches.csv。']
 (a.output/'逐例结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps({'cases':80,'batches':len(d['batches']),'output':str(a.output)}))

if __name__=='__main__':main()
