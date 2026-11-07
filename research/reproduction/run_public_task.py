"""One public task through the installed kernel and original Harbor; no matrix statistics."""
from pathlib import Path
import argparse,copy,json,types,time

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['prepared','gates','checkout','harbor','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--task-number',type=int,choices=range(1,5),default=4)
 p.add_argument('--docker-prefix',default='["docker"]');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
 from osa_eval.cli import run_pro
 from osa_eval.contracts import digest
 from official_regrade import configure,replay
 config=json.loads((a.prepared/'config.json').read_text());workload=json.loads((a.prepared/'workload.json').read_text());cpus=json.loads((a.prepared/'cpus.json').read_text());event=workload['events'][a.task_number-1];a.output.mkdir(parents=True,exist_ok=False)
 config=copy.deepcopy(config);config.update(architecture='single',seed=20261102,pro_checkout=str(a.checkout.resolve()));config['model']['seed']=20261102;config['limits']['token_budget']=32000000
 for name,value in [('config.json',config),('workload.json',{'events':[event]})]:(a.output/name).write_text(json.dumps(value,indent=2))
 if a.prepare_only:print(json.dumps({'prepared':True,'task':event['task_id'],'inference_calls':0}));return
 configure(a.checkout,a.harbor,json.loads(a.docker_prefix));run=a.output/'run';result=run_pro(types.SimpleNamespace(config=str(a.output/'config.json'),workload=str(a.output/'workload.json'),gates=str(a.gates),output=str(run)));assert result['status']=='completed'and result['usage']['accounting_valid'];score=replay(event['task_id'],run,a.output/'official-harbor'/digest(event['task_id'])[:20],cpus[event['task_id']]);receipt={'task':event['task_id'],'success':score['success'],'official_grade':score,'model_calls':len(result['usage']['calls']),'actual_api_tokens':result['usage']['actual_api_tokens'],'agent_wall_s':result['agent_wall_s'],'finished':time.time(),'scope':'Independent public reproduction acceptance; excluded from architecture comparison statistics'};(a.output/'acceptance.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

if __name__=='__main__':main()
