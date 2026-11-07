"""Evidence-bound interpretation of a full official verifier deadline failure.

No candidate, task, verifier, deadline or raw result is changed. Infrastructure
errors remain invalid. The original Harbor job metric is retained separately
from its absent per-trial reward. Missing test output is never called equal.
"""
from pathlib import Path
import hashlib,json
from datetime import datetime
from osa_eval.contracts import digest

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def duration(value):
 start=value.get('started_at');end=value.get('finished_at')
 assert start and end,value
 return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()

def adjudicate(task,run_dir,trial,job_result,proof,output):
 run_dir=Path(run_dir);output=Path(output)
 run=json.loads((run_dir/'result.json').read_text());row=next(x for x in run['rows']if x['task_id']==task.id);grade=row['grade'];identity=json.loads((run_dir/'identity.json').read_text());gate=identity['evaluator_gates'][task.id];reference=gate['reference'];empty=gate['empty'];deadline=float(task.config['verifier']['timeout_sec'])
 assert gate['passed'] and reference['valid'] is True and reference['success'] is True
 assert empty['valid'] is True and empty['success'] is False
 assert reference['task_files']==empty['task_files']==grade['task_files']==task.files
 image=grade['workspace']['image_id'];assert reference['workspace']['image_id']==empty['workspace']['image_id']==image==proof['image']
 assert grade['apply']['returncode']==0 and grade['execution']['returncode']==124
 assert grade['elapsed_s']>=deadline and grade['official_verifier_modified'] is False
 assert row['valid'] is False and row['success'] is None and not grade.get('infrastructure_failure')
 folder=run_dir/digest(task.id)[:20]/'pristine-grade'
 assert not(folder/'output.json').exists(),'A partial test output needs separate reconciliation'
 assert proof['actual']['cpu.max']=='100000 100000' and proof['actual']['memory.max']=='4294967296'
 exception=trial.get('exception_info')or{}
 assert exception.get('exception_type')=='VerifierTimeoutError',exception
 assert trial.get('verifier_result') is None,trial.get('verifier_result')
 elapsed=duration(trial['verifier']);assert elapsed>=deadline-1,(elapsed,deadline)
 metrics=[metric for value in job_result['stats']['evals'].values()for metric in value['metrics']]
 assert len(metrics)==1 and metrics[0].get('mean')==0,metrics
 assert job_result['n_total_trials']==1 and job_result['stats']['n_completed_trials']==1,job_result['stats']
 patch=run_dir/digest(task.id)[:20]/'model.patch';patchsha=sha(patch)
 assert patchsha==grade['patch_sha256']==run['captures'][task.id]['sha256']
 value={'schema_version':1,'raw_result_modified':False,'result_sha256':sha(run_dir/'result.json'),'task_id':task.id,'seed':row['seed'],'architecture':row['architecture'],'original_valid':False,'original_success':None,'interpreted_valid':True,'interpreted_success':False,'failure_category':'official_verifier_timeout','model_patch_sha256':patchsha,'image_id':image,'official_timeout_sec':deadline,'independent_elapsed_s':grade['elapsed_s'],'official_verifier_elapsed_s':elapsed,'official_exception_info':exception,'official_reward_raw':None,'official_aggregate_mean':0,'raw_test_output_comparison_available':False,'independent_reward_file_raw':(folder/'reward.txt').read_text().strip()if(folder/'reward.txt').exists()else None,'independent_reward_file_authoritative':False,'reference_success':True,'empty_success':False,'rule_sha256':sha(__file__),'rule':'Both fresh-image graders reach the unchanged official deadline after successful patch application; original Harbor reports VerifierTimeoutError and a one-trial job Mean0. Positive and empty controls match task and image. No test-output equality is asserted; unrelated infrastructure failures remain invalid.'}
 output.mkdir(exist_ok=False);(output/'annotation.json').write_text(json.dumps(value,indent=2));return value
