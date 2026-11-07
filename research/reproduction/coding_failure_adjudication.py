"""Preserve raw grades and prove code-caused Python collection failures."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,subprocess
from osa_eval.contracts import digest
from osa_eval.swebench_pro import compiler_crashes
from m2_syntax_adjudication042 import adjudicate as syntax_adjudicate

IMPORT_PROBE=r'''from pathlib import Path
import sys,os,json,subprocess,tempfile,hashlib
d=json.loads(sys.stdin.buffer.read());cwd=d['cwd'];name=d['path'];module=d['module'];p=Path('/sys/fs/cgroup');record={'cpu.max':(p/'cpu.max').read_text().strip(),'memory.max':(p/'memory.max').read_text().strip(),'affinity':sorted(os.sched_getaffinity(0))}
env=dict(os.environ,PYTHONPATH=cwd+os.pathsep+os.environ.get('PYTHONPATH',''))
def probe():
 x=subprocess.run([sys.executable,'-c','import importlib;importlib.import_module('+repr(module)+')'],cwd=cwd,env=env,capture_output=True,text=True,timeout=60)
 return {'returncode':x.returncode,'stdout':x.stdout[-4000:],'stderr':x.stderr[-8000:]}
record['baseline_source_sha256']=hashlib.sha256(Path(name).read_bytes()).hexdigest();record['baseline']=probe()
assert record['baseline']['returncode']==0,record['baseline']
with tempfile.TemporaryDirectory(prefix='osa-import-proof-')as tmp:
 patch=Path(tmp)/'model.patch';patch.write_text(d['patch'],encoding='utf-8');commands=[['git','apply','--verbose',str(patch)],['git','apply','--3way',str(patch)],['patch','--fuzz=3','-p1','-i',str(patch)]]
 for command in commands:
  x=subprocess.run(command,cwd=cwd,capture_output=True,timeout=30)
  if x.returncode==0:break
 assert x.returncode==0,x.stderr.decode(errors='replace')[-2000:]
record['apply_exit']=0;record['patched_source_sha256']=hashlib.sha256(Path(name).read_bytes()).hexdigest();record['patched']=probe();print(json.dumps(record))
'''

def adjudicate(task_id,run_dir,output,cpu,docker_prefix):
 run_dir=Path(run_dir);folder=run_dir/digest(task_id)[:20]/'pristine-grade';logs='\n'.join((folder/n).read_text(errors='replace')for n in ['run-script-stdout.txt','run-script-stderr.txt']if(folder/n).exists())
 if re.search(r'\b(?:SyntaxError|IndentationError|TabError):',logs):return syntax_adjudicate(task_id,run_dir,output,cpu,docker_prefix)
 output=Path(output);output.mkdir(exist_ok=False);run=json.loads((run_dir/'result.json').read_text());row=next(x for x in run['rows']if x['task_id']==task_id);grade=row['grade'];identity=json.loads((run_dir/'identity.json').read_text());gate=identity['evaluator_gates'][task_id];reference=gate['reference'];empty=gate['empty'];assert gate['passed']and reference['valid']is True and reference['success']is True and empty['valid']is True and empty['success']is False
 assert reference['task_files']==empty['task_files']==grade['task_files'];image=grade['workspace']['image_id'];assert image==reference['workspace']['image_id']==empty['workspace']['image_id'];assert row['valid']is False and row['success']is None and grade['apply']['returncode']==0
 assert json.loads((folder/'output.json').read_text()).get('tests')==[]and(folder/'reward.txt').read_text().strip()=='0';assert not compiler_crashes(logs)
 errors=re.findall(r'(?m)^(?:E\s+)?((?:TypeError|NameError|AttributeError|ImportError|ModuleNotFoundError|ValueError|RuntimeError|KeyError|IndexError): .+)$',logs);assert errors,'No definite supported Python import exception; preserve invalid grade';error=errors[-1];patch=run_dir/digest(task_id)[:20]/'model.patch';patchsha=hashlib.sha256(patch.read_bytes()).hexdigest();assert patchsha==grade['patch_sha256']==run['captures'][task_id]['sha256'];changed=[line[6:]for line in patch.read_text().splitlines()if line.startswith('+++ b/')and line.endswith('.py')];candidates=[p for p in changed if re.search(re.escape(p)+r':\d+: in ',logs)];assert candidates,'Import traceback does not identify a model-modified file';relative=PurePosixPath(candidates[-1]);assert not relative.is_absolute()and'..'not in relative.parts;cwd=PurePosixPath(grade['workspace']['cwd']);path=cwd/relative;module='.'.join(relative.with_suffix('').parts);assert all(p.isidentifier()for p in module.split('.'))
 command=[*docker_prefix,'run','--rm','-i','--network','none','--cpus','1','--memory','4294967296','--cpuset-cpus',str(cpu),'--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','python3',image,'-c',IMPORT_PROBE];body=json.dumps({'cwd':str(cwd),'path':str(path),'module':module,'patch':patch.read_text()}).encode();x=subprocess.run(command,input=body,capture_output=True,timeout=180);(output/'import-probe.stdout').write_bytes(x.stdout);(output/'import-probe.stderr').write_bytes(x.stderr);assert x.returncode==0,x.stderr.decode(errors='replace')[-2000:];proof=json.loads(x.stdout);assert proof['baseline']['returncode']==0 and proof['patched']['returncode']!=0 and error in proof['patched']['stderr'];assert proof['baseline_source_sha256']!=proof['patched_source_sha256'];assert proof['cpu.max']=='100000 100000'and proof['memory.max']=='4294967296'and proof['affinity']==[cpu]
 value={'schema_version':1,'raw_result_modified':False,'result_sha256':hashlib.sha256((run_dir/'result.json').read_bytes()).hexdigest(),'task_id':task_id,'seed':row['seed'],'architecture':row['architecture'],'original_valid':False,'original_success':None,'interpreted_valid':True,'interpreted_success':False,'failure_category':'model_introduced_python_import_error','diagnostic':error,'changed_import_module':module,'source_path':str(path),'model_patch_sha256':patchsha,'same_image_import_probe':proof,'image_id':image,'rule_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'rule':'Positive and empty controls match task/image; independent reward0 with no collected tests; traceback identifies a model-modified module. Fresh same-image baseline imports, exact captured patch imports fail with the same definite Python exception, actual1CPU4GiB. Final acceptance additionally requires original Harbor reward0/noexception/equaltestoutcome. Unexplained and infrastructure errors remain invalid.'};(output/'annotation.json').write_text(json.dumps(value,indent=2));return value
