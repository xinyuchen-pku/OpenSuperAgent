"""Original Harbor scoring of frozen model artifacts on the accepted local backend."""
from pathlib import Path
import os,json,subprocess,time,hashlib
from osa_eval.contracts import digest
from coding_failure_adjudication import adjudicate
R=Path(__file__).resolve().parent
CHECKOUT=None
HARBOR=None
PRE=None
def configure(checkout,harbor,docker_prefix):
 global CHECKOUT,HARBOR,PRE
 CHECKOUT=Path(checkout).resolve();HARBOR=str(Path(harbor).resolve());PRE=list(docker_prefix)
 assert CHECKOUT.is_dir() and Path(HARBOR).is_file() and PRE
 assert subprocess.check_output(['git','-C',str(CHECKOUT),'rev-parse','HEAD'],text=True).strip()=='66f92766bba642462d4bbe5479e83f91f9211862'
 assert subprocess.run(['git','-C',str(CHECKOUT),'diff','--quiet','HEAD','--']).returncode==0
 python=Path(HARBOR).parent/'python'
 assert python.is_file(),'Use the harbor executable inside its pinned virtual environment'
 code="import importlib.metadata as m,json;d=m.distribution('harbor');print(json.dumps({'version':d.version,'direct_url':json.loads(d.read_text('direct_url.json')or'{}')}))"
 identity=json.loads(subprocess.check_output([str(python),'-c',code],text=True));url=identity['direct_url'];commit=url.get('vcs_info',{}).get('commit_id')
 if commit is None and url.get('dir_info',{}).get('editable'):
  from urllib.parse import urlparse,unquote
  source=unquote(urlparse(url['url']).path);commit=subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip();assert subprocess.run(['git','-C',source,'diff','--quiet','HEAD','--']).returncode==0
 assert commit=='f6cf2e2e86a102a9d2980ce8888f4bda251aa998',identity
def environment():
 env=dict(os.environ,PYTHONPATH=str(R)+os.pathsep+str(CHECKOUT/'v2/tooling')+os.pathsep+os.environ.get('PYTHONPATH',''),LITELLM_LOCAL_MODEL_COST_MAP='True')
 for name in list(env):
  if name.startswith('LLM_') or name in {'OPENAI_API_KEY','ANTHROPIC_API_KEY'}:env.pop(name,None)
 return env

def actual_resources(task_id,image,cpu):
 ids=subprocess.check_output([*PRE,'ps','-q','--filter','label=com.docker.compose.service=main','--filter','ancestor='+image],text=True,timeout=10).split();matches=[]
 for id in ids:
  info=json.loads(subprocess.check_output([*PRE,'inspect',id],text=True,timeout=10))[0];labels=info['Config'].get('Labels')or{}
  if task_id in labels.get('com.docker.compose.project.working_dir','')and info['Image']==image and info['State']['Running']and info['HostConfig']['CpusetCpus']==str(cpu):matches.append(info)
 if not matches:return None
 assert len(matches)==1,'Ambiguous task ownership';info=matches[0];code="from pathlib import Path;import os,json;p=Path('/sys/fs/cgroup');print(json.dumps({'cpu.max':(p/'cpu.max').read_text().strip(),'memory.max':(p/'memory.max').read_text().strip(),'cpuset.cpus.effective':(p/'cpuset.cpus.effective').read_text().strip(),'affinity':sorted(os.sched_getaffinity(0))}))";x=subprocess.run([*PRE,'exec',info['Id'],'python3','-c',code],capture_output=True,text=True,timeout=20)
 if x.returncode:return None
 actual=json.loads(x.stdout);assert actual['cpu.max']=='100000 100000'and actual['memory.max']=='4294967296'and actual['affinity']==[cpu],actual;return{'container_id':info['Id'],'image':image,'actual':actual,'host_limits':{k:info['HostConfig'].get(k)for k in ['NanoCpus','Memory','CpusetCpus','MemorySwap']},'time':time.time()}

def source_identity(run_dir):
 identity=json.loads((Path(run_dir)/'identity.json').read_text());source=identity['source'];manifest=source.get('frozen_manifest')
 if manifest is not None:
  canonical=json.dumps(manifest['files'],sort_keys=True,separators=(',',':')).encode();assert hashlib.sha256(canonical).hexdigest()==manifest['tree_sha256'];return manifest['tree_sha256']
 manifest=json.loads((R/'research-source-manifest.json').read_text());expected={p.removeprefix('osa_eval/'):sha for p,sha in manifest['files'].items()if p.startswith('osa_eval/')and Path(p).suffix in {'.py','.mjs'}};assert source['modules']==expected,'Captured installed module hashes differ from the delivered frozen source';return manifest['tree_sha256']

def replay(task_id,run_dir,output,cpu,precomputed=None):
 from osa_eval.swebench_pro import ProTask
 from official_timeout_adjudication import adjudicate as timeout_adjudicate
 import shutil
 run_dir=Path(run_dir);output=Path(output);run=json.loads((run_dir/'result.json').read_text());assert run['status']=='completed';row=next(x for x in run['rows']if x['task_id']==task_id);task=ProTask(CHECKOUT/'v2/tasks'/task_id);assert task.files==row['grade']['task_files'];image=row['grade']['workspace']['image_id'];assert subprocess.check_output([*PRE,'image','inspect',image,'--format','{{.Id}}'],text=True).strip()==image;subprocess.run([*PRE,'tag',image,task.image],check=True,capture_output=True)
 patch=run_dir/digest(task_id)[:20]/'model.patch';patchsha=hashlib.sha256(patch.read_bytes()).hexdigest();assert patchsha==run['captures'][task_id]['sha256'];output.mkdir(parents=True,exist_ok=False);annotation=None;start=time.monotonic()
 is_timeout=row['valid'] is False and row['grade'].get('execution',{}).get('returncode')==124
 if row['valid'] is not True and not is_timeout:annotation=adjudicate(task_id,run_dir,output/'syntax-adjudication',cpu,PRE)
 if precomputed is None:
  overlay=output/'cpu-placement.json';overlay.write_text(json.dumps({'services':{'main':{'cpuset':str(cpu)}}}));job='patch-'+hashlib.sha256(str(output).encode()).hexdigest()[:14];cmd=[HARBOR,'run','-p',str(task.path),'-e','docker','-n','1','-a','m2_patch_replay001:FrozenPatchReplayAgent','--extra-docker-compose',str(overlay),'--agent-kwarg','patch_path='+str(patch),'--agent-kwarg','patch_sha256='+patchsha,'--job-name',job,'--jobs-dir',str(output/'jobs')];(output/'command.json').write_text(json.dumps(cmd));proof=None
  with(output/'run.log').open('wb')as f:
   child=subprocess.Popen(cmd,env=environment(),stdout=f,stderr=subprocess.STDOUT)
   (output/'process.json').write_text(json.dumps({'pid':child.pid,'start_ticks':Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()[19],'argv_sha256':hashlib.sha256(Path(f'/proc/{child.pid}/cmdline').read_bytes()).hexdigest(),'command':cmd}))
   while child.poll() is None:
    if proof is None:
     proof=actual_resources(task_id,image,cpu)
     if proof:(output/'resource-proof.json').write_text(json.dumps(proof,indent=2))
    if time.monotonic()-start>float(task.config['verifier']['timeout_sec'])+900:raise TimeoutError('Original Harbor exceeded its official deadline plus setup allowance; inspect exact process record')
    time.sleep(.5)
  assert child.returncode==0,(output/'run.log').read_text(errors='replace')[-1600:]
  assert proof is not None;jobroot=output/'jobs'/job;reused=None
 else:
  source=Path(precomputed);receipt=json.loads((source/'ARCHIVE_RECEIPT.json').read_text());assert receipt['all_raw_bytes_equal'];assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==sha for name,sha in receipt['files'].items());record=json.loads((source/'receipt.json').read_text());cmd=json.loads((source/'command.json').read_text());assert Path(cmd[0]).resolve()==Path(HARBOR).resolve() and cmd[cmd.index('-p')+1]==str(task.path) and cmd[cmd.index('-a')+1]=='m2_patch_replay001:FrozenPatchReplayAgent';assert 'patch_sha256='+patchsha in cmd and record['patch_sha256']==patchsha and record['task_id']==task_id;assert record['original_harbor_commit']=='f6cf2e2e86a102a9d2980ce8888f4bda251aa998' and record['official_timeout_sec']==task.config['verifier']['timeout_sec'];assert not any('timeout-multiplier' in x for x in cmd);assert record['CLI_exit']==0
  copied=output/'precomputed-original';shutil.copytree(source,copied);assert all(hashlib.sha256((copied/name).read_bytes()).hexdigest()==sha for name,sha in receipt['files'].items());proof=record['resource_proof'];job=cmd[cmd.index('--job-name')+1];jobroot=copied/'jobs'/job;reused={'directory':str(source),'archive_receipt_sha256':hashlib.sha256((source/'ARCHIVE_RECEIPT.json').read_bytes()).hexdigest(),'all_raw_bytes_equal':True,'model_calls':0,'original_elapsed_s':record['elapsed_s']}
 trials=[]
 for p in jobroot.rglob('result.json'):
  d=json.loads(p.read_text())
  if 'verifier_result' in d:trials.append((p,d))
 assert len(trials)==1;trial,d=trials[0];aggregate=json.loads((jobroot/'result.json').read_text());official=trial.parent/'verifier/output.json';independent=run_dir/digest(task_id)[:20]/'pristine-grade/output.json'
 if is_timeout:
  annotation=timeout_adjudicate(task,run_dir,d,aggregate,proof,output/'timeout-adjudication');success=False;reward=None;raw_equal=None;outcomes_equal=None;officialsha=independentsha=None;independent_success=False
 else:
  assert d.get('exception_info') is None,d.get('exception_info');reward=d['verifier_result']['rewards']['reward'];a=json.loads(official.read_text());b=json.loads(independent.read_text());normalize=lambda value:sorted((x['name'],x['status'])for x in value['tests']);assert normalize(a)==normalize(b),'Original/independent test outcomes differ';independent_success=False if annotation else row['success'];assert bool(reward)==independent_success;success=bool(reward);raw_equal=official.read_bytes()==independent.read_bytes();outcomes_equal=True;officialsha=hashlib.sha256(official.read_bytes()).hexdigest();independentsha=hashlib.sha256(independent.read_bytes()).hexdigest()
 attestation={'official_protocol_valid':True,'scope':'This captured model artifact, task, architecture and seed only','task_id':task_id,'architecture':row['architecture'],'seed':row['seed'],'success':success,'official_reward':reward,'official_aggregate_mean':annotation['official_aggregate_mean'] if is_timeout else reward,'independent_success':independent_success,'independent_original_valid':row['valid'],'coding_failure_adjudication':annotation,'raw_output_equal':raw_equal,'test_outcomes_equal':outcomes_equal,'official_output_sha256':officialsha,'independent_output_sha256':independentsha,'model_patch_sha256':patchsha,'image_id':image,'source_tree_sha256':source_identity(run_dir),'original_harbor_commit':'f6cf2e2e86a102a9d2980ce8888f4bda251aa998','official_task_verifier_modified':False,'actual_resources':proof,'elapsed_s':time.monotonic()-start,'trial':str(trial),'raw_campaign_protocol_flag_preserved':run['official_protocol_valid'],'precomputed_original_harbor':reused,'grading_rule_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};(output/'protocol-attestation.json').write_text(json.dumps(attestation,indent=2));return attestation

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description='Original pinned Harbor regrade of every captured task artifact; no inference requests.')
 p.add_argument('--checkout',required=True);p.add_argument('--harbor',required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--docker-prefix',default='["docker"]');p.add_argument('--task-id',action='append',help='Regrade selected exact task ID(s); default all captured tasks');p.add_argument('--cpus',required=True,help='JSON mapping from exact task ID to allowed Docker-host CPU index')
 args=p.parse_args();configure(args.checkout,args.harbor,json.loads(args.docker_prefix));placement=json.loads(args.cpus);run=json.loads((args.run/'result.json').read_text());args.output.mkdir(exist_ok=False);records=[]
 selected=[row for row in run['rows']if args.task_id is None or row['task_id']in args.task_id];assert selected
 for row in selected:records.append(replay(row['task_id'],args.run,args.output/__import__('osa_eval.contracts',fromlist=['digest']).digest(row['task_id'])[:20],placement[row['task_id']]))
 (args.output/'official-scores.json').write_text(json.dumps(records,indent=2));print(json.dumps({'valid':True,'tasks':len(records),'successes':sum(x['success']for x in records)}))
