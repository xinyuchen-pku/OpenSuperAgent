"""One frozen capability case with source025 or the pinned upstream mini agent.

The host supplies credentials and Docker transport. Neither enters the task.
Use --prepare-only to validate the resolved plan without inference or containers.
"""
from pathlib import Path
import argparse, asyncio, hashlib, json, os, sys, time, traceback


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['config','gates','checkout','harbor','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--agent',choices=['source025','mini'],required=True)
    parser.add_argument('--task-id',required=True)
    parser.add_argument('--mini-checkout',type=Path)
    parser.add_argument('--cpu-index',type=int,default=0)
    parser.add_argument('--docker-prefix',default='["docker"]')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    from osa_eval.contracts import Limits,Event,canonical,digest
    from osa_eval.kernel import Kernel
    from osa_eval.journal import Journal
    from osa_eval.model import ChatModel
    from osa_eval.swebench_pro import ProTask
    from osa_eval.workspace import DockerWorkspace
    from osa_eval.benchmarks import verify_checkout
    from official_regrade import configure,replay
    import subprocess
    root=Path(__file__).resolve().parents[1]
    config=json.loads(args.config.read_text());gates=json.loads(args.gates.read_text())
    assert args.task_id in config['tasks_in_fixed_order']
    task=ProTask(args.checkout/'v2/tasks'/args.task_id);gate=gates[task.id]
    verify_checkout(args.checkout,'swebench_pro')
    assert gate['passed']and task.files==gate['task_files']
    assert gate['reference']['valid']and gate['reference']['success']is True
    assert gate['empty']['valid']and gate['empty']['success']is False
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text())
    import osa_eval
    installed=Path(osa_eval.__file__).parent
    assert all(hashlib.sha256((installed/n.removeprefix('osa_eval/')).read_bytes()).hexdigest()==h
               for n,h in manifest['files'].items()if n.startswith('osa_eval/'))
    limits=Limits(slots=1,model_concurrency=1,token_budget=2000000,request_token_reservation=262144,
                  reservation_policy='exact_prompt_plus_max_output',max_steps=100,tool_timeout_s=120,task_timeout_s=3600)
    if args.agent=='mini':
        assert args.mini_checkout is not None
        assert subprocess.check_output(['git','-C',str(args.mini_checkout),'rev-parse','HEAD'],text=True).strip()==config['standard_agent']['commit']
        assert subprocess.run(['git','-C',str(args.mini_checkout),'diff','--quiet','HEAD','--']).returncode==0
        sys.path.insert(0,str(args.mini_checkout/'src'))
    identity={'architecture':'single'if args.agent=='source025'else'mini_swe_agent','seed':20261102,
              'source':{'frozen_manifest':manifest},'task_id':task.id,'task_files':task.files,
              'agent':args.agent,'limits':limits.public(),'model':config['model'],
              'mini_commit':config['standard_agent']['commit'],'worker_prompt_modified':False}
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'identity.json').write_text(canonical(identity))
    os.environ.setdefault('MSWEA_SILENT_STARTUP','1')
    os.environ.setdefault('MSWEA_GLOBAL_CONFIG_DIR',str(args.output.resolve()/'mini-config'))
    os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP','True')
    if args.prepare_only:
        print(canonical({'prepared':True,'actual_api_calls':0,'identity':identity}));return
    model=ChatModel(api_key=os.environ[config.get('api_key_env','LLM_API_KEY')],**config['model'])
    prefix=json.loads(args.docker_prefix)
    assert prefix and all(isinstance(p,str)and p for p in prefix)
    os.environ['DOCKER_HOST']=config.get('docker_endpoint',os.environ.get('DOCKER_HOST','unix:///var/run/docker.sock'))
    placed=[sys.executable,str(Path(__file__).resolve()),'--docker-command',str(args.cpu_index),json.dumps(prefix)]
    configure(args.checkout,args.harbor,prefix)
    # TLS and client configuration remain in the host environment, as in the matrix runner.
    def factory(purpose,label):
        return DockerWorkspace.create(image=gate['image_id'],name='osa-cap-'+digest([str(args.output),label])[:20],
            purpose=purpose,cpus=1,memory_mb=4096,command_prefix=placed)
    journal=Journal(args.output/'run.sqlite3',token_budget=2000000,identity=identity)
    journal.intake(Event(task.id,task.id,task.instruction,task_id=task.id))
    journal.assign(Event(task.id,task.id,task.instruction,task_id=task.id),task.id,'main','worker')
    workspace=factory('agent','agent');began=time.monotonic();folder=args.output/digest(task.id)[:20];folder.mkdir()
    try:
        for field in ['backend','cgroup_limits_enforced','cpus','memory_mb']:
            assert workspace.identity[field]==gate['reference']['workspace'][field],field
        asyncio.run(task.prepare_agent(workspace))
        try:
            if args.agent=='mini':
                import yaml
                from capability_adapter import mini_work
                mini_config=yaml.safe_load((args.mini_checkout/'src/minisweagent/config/mini.yaml').read_text())
                claim=mini_work(model,journal,workspace,task,limits,mini_config,args.output)
            else:
                claim=asyncio.run(Kernel(model,journal,limits).work(task.id,task.instruction,workspace,
                                  session='main',execution_timeout_s=3600))
            journal.complete_task(task.id,canonical(claim)if isinstance(claim,dict)else claim)
        except Exception as error:
            journal.task_state(task.id,'blocked',type(error).__name__+':'+str(error))
            (args.output/'agent-exception.txt').write_text(traceback.format_exc())
        assert journal.usage()['accounting_valid'],'Unknown provider usage; preserve evidence and reconcile'
        patch=folder/'model.patch';capture=asyncio.run(task.capture_patch(workspace,patch))
        captures={task.id:{'patch':str(patch),**capture,'submitted_s':time.monotonic()-began}}
    finally:
        workspace.stop();journal.export(args.output)
    grade=asyncio.run(task.grade(lambda:factory('verifier','grade'),patch,folder/'pristine-grade'))
    result={'status':'completed','official_protocol_valid':False,'rows':[{'task_id':task.id,
            'architecture':identity['architecture'],'seed':20261102,'success':grade['success'],'valid':grade['valid'],'grade':grade}],
            'captures':captures,'usage':journal.usage(),'agent_wall_s':captures[task.id]['submitted_s']}
    (args.output/'result.json').write_text(canonical(result))
    score=replay(task.id,args.output,args.output/'official-harbor'/digest(task.id)[:20],args.cpu_index)
    (args.output/'accepted-summary.json').write_text(canonical({'official':score,'usage':result['usage']}))
    print(canonical({'success':score['success'],'official_protocol_valid':score['official_protocol_valid'],
                     'actual_api_tokens':result['usage']['actual_api_tokens']}))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--docker-command':
        cpu,prefix,*command=sys.argv[2:];prefix=json.loads(prefix)
        assert cpu.isdecimal()and int(cpu)>=0 and command and prefix
        if command[0]=='run':command=['run','--cpuset-cpus',cpu,*command[1:]]
        os.execvp(prefix[0],[*prefix,*command])
    else:main()
