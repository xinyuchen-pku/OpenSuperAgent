"""Environment preflight; no coding instructions or task files are changed."""
import asyncio
import json
import shlex
import threading
from pathlib import Path

from osa_eval.workspace import AsynWorkspace

_GIT_LOCK = threading.Lock()


def prepare_native_identity(request):
    async def run():
        workspace = AsynWorkspace(request.workspace, request.workspace_path, {'backend': 'asyncodebench'})
        script = '''import subprocess,json
run=lambda a:subprocess.run(['git',*a],capture_output=True,text=True)
before=run(['rev-parse','HEAD']);assert before.returncode==0
for key,value in [('user.name','OpenSuperAgent Benchmark'),('user.email','worker@example.invalid')]:
 p=run(['config','--local',key,value]);assert p.returncode==0,p.stderr
check=run(['var','GIT_COMMITTER_IDENT']);assert check.returncode==0,check.stderr
after=run(['rev-parse','HEAD']);assert before.stdout==after.stdout
print(json.dumps(dict(passed=True,tracked_head_unchanged=True,identity_scope='repository-local shared by original private worktrees and integrator',git_committer_ident=check.stdout.strip())))
'''
        result = await workspace.execute('python -I -c ' + shlex.quote(script), 30)
        if result['returncode']:
            raise RuntimeError('Native Git identity preflight failed: ' + result['stderr'])
        return json.loads(result['stdout'])
    with _GIT_LOCK:
        proof = asyncio.run(run())
    output = Path(request.output_dir) / 'native-environment-preflight'
    output.mkdir(exist_ok=True)
    (output / (request.assignment_id + '.json')).write_text(json.dumps(proof, indent=2), encoding='utf-8')
    return proof
