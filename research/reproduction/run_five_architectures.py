"""Five controlled architectures, original Harbor scores, and the fixed M2 stop rule.

Run with the source022 wheel installed. Supply a source022 M2 configuration,
the four-task frozen workload, admitted gates, and the original pinned Harbor.
Credentials stay in the configuration's named host environment variable.
Use --prepare-only to inspect every configuration without inference.
"""
from pathlib import Path
import argparse,copy,json,types,time,hashlib

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['config','workload','gates','output','checkout','harbor','cpus']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--docker-prefix',default='["docker"]');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
 from osa_eval.campaign import balanced_arm_order
 from osa_eval.cli import run_pro
 from osa_eval.contracts import digest
 from official_regrade import configure,replay
 config=json.loads(a.config.read_text());workload=json.loads(a.workload.read_text());gates=json.loads(a.gates.read_text());cpus=json.loads(a.cpus.read_text());events=workload['events'];ids=[e['task_id']for e in events]
 assert len(ids)==4 and len(set(ids))==4 and all(e['arrival_s']==0 for e in events)
 assert config['limits']['token_budget']==128000000 and config['limits']['max_steps']==100 and config['limits']['reservation_policy']=='exact_prompt_plus_max_output'
 assert all(gates[t]['passed']for t in ids);assert set(cpus)==set(ids);assert len(set(cpus.values()))==4
 assert config['model']['max_output_tokens']==8192 and config['model']['tokenizer_preflight'] is True
 a.output.mkdir(parents=True,exist_ok=False);configure(a.checkout,a.harbor,json.loads(a.docker_prefix));seeds=[20261102,20261103,20261104];order=balanced_arm_order(3,seed=20261102);jobs=[]
 def add(arm,seed,chosen,section,label):jobs.append({'architecture':arm,'seed':seed,'task_ids':chosen,'section':section,'label':label})
 add('single',seeds[0],[ids[2]],'secondary','seed20261102-single-task003')
 for block,seed in enumerate(seeds):
  for arm in order[block]:add(arm,seed,ids,'primary',f'seed{seed}-{arm}')
 for arm in order[0]:
  for i,t in enumerate(ids):
   if arm=='single'and i==2:continue
   add(arm,seeds[0],[t],'secondary',f'seed20261102-{arm}-task{i+1:03d}')
 plan={'created':time.time(),'jobs':jobs,'config_sha256':hashlib.sha256(a.config.read_bytes()).hexdigest(),'workload_sha256':hashlib.sha256(a.workload.read_bytes()).hexdigest(),'gates_sha256':hashlib.sha256(a.gates.read_bytes()).hexdigest(),'primary_grades':60,'secondary_grades':20,'first20_allzero':'Stop and diagnose before further seeds.','scope':'Frozen source022 task-level implementations. Native AsynCodeBench is a separate protocol axis.'};(a.output/'plan.json').write_text(json.dumps(plan,indent=2));prepared=[]
 for job in jobs:
  name=job['section']+'-'+job['label'];dest=a.output/'prepared'/name;dest.mkdir(parents=True);c=copy.deepcopy(config);c.update(architecture=job['architecture'],seed=job['seed'],pro_checkout=str(a.checkout.resolve()));c['model']['seed']=job['seed']
  if job['section']=='secondary':c['limits']['token_budget']=32000000
  w={'events':[e for e in events if e['task_id']in job['task_ids']]};(dest/'config.json').write_text(json.dumps(c,indent=2));(dest/'workload.json').write_text(json.dumps(w,indent=2));prepared.append((job,dest))
 if a.prepare_only:print(json.dumps({'prepared':len(prepared),'inference_requests':0,'plan':str(a.output/'plan.json')}));return
 accepted=[]
 for job,prepared_dir in prepared:
  output=a.output/job['section']/job['label'];output.parent.mkdir(exist_ok=True);run=run_pro(types.SimpleNamespace(config=str(prepared_dir/'config.json'),workload=str(prepared_dir/'workload.json'),gates=str(a.gates),output=str(output)));assert run['status']=='completed'and run['usage']['accounting_valid'];scores=[]
  for row in run['rows']:scores.append(replay(row['task_id'],output,output/'official-harbor'/digest(row['task_id'])[:20],cpus[row['task_id']]))
  receipt={**job,'successes':sum(x['success']for x in scores),'scores':scores,'actual_api_tokens':run['usage']['actual_api_tokens'],'agent_wall_s':run['agent_wall_s']};(output/'accepted-summary.json').write_text(json.dumps(receipt,indent=2));accepted.append(receipt);(a.output/'progress.json').write_text(json.dumps(accepted,indent=2))
  first=[x for x in accepted if x['section']=='primary'and x['seed']==seeds[0]]
  if len(first)==5 and job['section']=='primary'and job['seed']==seeds[0]and sum(x['successes']for x in first)==0:
   (a.output/'diagnosis-required.json').write_text(json.dumps({'reason':'First20 valid primary grades allzero; inspect model capability, tasks, budgets and raw failures before more seeds.'}));print('Stopped at the predeclared diagnostic gate.');return
 (a.output/'complete.json').write_text(json.dumps({'primary_grades':60,'secondary_grades':20,'finished':time.time()}))
if __name__=='__main__':main()
