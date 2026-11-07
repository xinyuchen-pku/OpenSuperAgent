"""Prepare the fixed M2 workload and configuration; performs no inference."""
from pathlib import Path
import argparse,json,sys
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkout',type=Path,required=True);p.add_argument('--docker-client',type=Path,required=True);p.add_argument('--docker-endpoint',default='unix:///var/run/docker.sock');p.add_argument('--cpu-indices',default='0,1,2,3');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 from osa_eval.benchmarks import verify_checkout
 from osa_eval.swebench_pro import ProTask
 root=Path(__file__).resolve().parent;verify_checkout(a.checkout,'swebench_pro');matrix=json.loads((root/'m2-matrix.json').read_text());config=json.loads((root/'controlled-pro.m2.template.json').read_text());images=json.loads((root/'official-image-identities.json').read_text());cpus=[int(x)for x in a.cpu_indices.split(',')];assert len(cpus)==4 and len(set(cpus))==4 and min(cpus)>=0;a.output.mkdir(parents=True,exist_ok=False);config['pro_checkout']=str(a.checkout.resolve());config['workspace_backend']['command_prefix_by_task']={t:[sys.executable,str(root/'docker_cpu_prefix.py'),str(cpu),str(a.docker_client.resolve()),a.docker_endpoint]for t,cpu in zip(matrix['task_ids'],cpus)};events=[]
 for t in matrix['task_ids']:events.append({'id':t,'thread':t,'task_id':t,'text':ProTask(a.checkout/'v2/tasks'/t).instruction,'arrival_s':0,'kind':'request'})
 for name,value in [('config.json',config),('workload.json',{'events':events}),('cpus.json',dict(zip(matrix['task_ids'],cpus))),('images.json',{t:row for t,row in zip(matrix['task_ids'],images)})]:(a.output/name).write_text(json.dumps(value,indent=2))
 print(json.dumps({'prepared':True,'directory':str(a.output.resolve()),'next':'Fill model endpoint/identity inconfig.json; load key viaLLM_API_KEY; qualify environment before model runs.'}))
if __name__=='__main__':main()
