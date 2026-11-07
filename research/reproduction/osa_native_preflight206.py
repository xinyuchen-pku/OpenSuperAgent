"""Common trusted Git merge preflight; use for every future native Worker arm."""
from pathlib import Path
import asyncio,json,threading
from osa_eval.workspace import AsynWorkspace
from osa_eval.asyncodebench_adapter import SharedWorkerAdapter
_LOCK=threading.Lock()
def prepare_native_identity(request):
    async def run():
        ws=AsynWorkspace(request.workspace,request.workspace_path,{'backend':'asyncodebench'})
        command="python -I -c "+__import__('shlex').quote('''import subprocess,json
run=lambda a:subprocess.run(['git',*a],capture_output=True,text=True)
before=run(['rev-parse','HEAD']);assert before.returncode==0
for key,value in [('user.name','OpenSuperAgent Benchmark'),('user.email','worker@example.invalid')]:
 p=run(['config','--local',key,value]);assert p.returncode==0,p.stderr
check=run(['var','GIT_COMMITTER_IDENT']);assert check.returncode==0,check.stderr
after=run(['rev-parse','HEAD']);assert before.stdout==after.stdout
print(json.dumps(dict(passed=True,tracked_head_unchanged=True,identity_scope='repository-local shared by original private worktrees and integrator',git_committer_ident=check.stdout.strip())))
''')
        r=await ws.execute(command,30)
        if r['returncode']:raise RuntimeError('Native Git merge identity preflight failed: '+r['stderr'])
        return json.loads(r['stdout'])
    with _LOCK:proof=asyncio.run(run())
    out=Path(request.output_dir)/'native-environment-preflight';out.mkdir(exist_ok=True);(out/(request.assignment_id+'.json')).write_text(json.dumps(proof,indent=2));return proof
class PreparedSharedWorkerAdapter(SharedWorkerAdapter):
    name='osa-shared-worker-with-native-environment-preflight'
    def execute(self,request):
        proof=prepare_native_identity(request)
        response=super().execute(request)
        response.metadata['native_environment_preflight']=proof
        return response
