import asyncio,json,subprocess,tempfile,unittest,shlex,sys
from pathlib import Path
from osa_eval.artifact_validation import ArtifactValidation

class Workspace:
    def __init__(self,root):self.root=root;self.commands=[]
    async def execute(self,command,timeout_s):
        self.commands.append(command)
        if command.startswith('python3 -I -c '):argv=[sys.executable,*shlex.split(command)[1:]]
        elif command.startswith('git '):argv=shlex.split(command)
        else:
            bash=Path('C:/Program Files/Git/bin/bash.exe');argv=[str(bash)if bash.exists()else'bash','-c',command]
        p=await asyncio.to_thread(subprocess.run,argv,cwd=self.root,capture_output=True,text=True,timeout=timeout_s)
        return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

class ArtifactGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.file=self.root/'a.py';self.file.write_text('answer=1\n');subprocess.run(['git','init','-q',str(self.root)],check=True)
        for args in [['add','.'],['-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline']]:subprocess.run(['git','-C',str(self.root),*args],check=True)
        self.workspace=Workspace(self.root);self.command=shlex.quote(sys.executable.replace('\\','/'))+' -c '+shlex.quote("from pathlib import Path;compile(Path('a.py').read_text(),'a.py','exec')")
    def tearDown(self):self.temp.cleanup()
    async def test_success_is_invalidated_by_later_edit_and_current_syntax_failure_is_reported(self):
        gate=ArtifactValidation(self.workspace,[self.command]);first=await gate.validate_current();self.assertTrue(first['passed']);self.file.write_text('answer=(\n');gate.observe(await gate.fingerprint());self.assertIsNone(gate.validated_revision);result=await gate.validate_current();self.assertFalse(result['passed']);self.assertFalse(result['benchmark_success_claimed']);self.assertIn('SyntaxError',result['checks']['stderr'])
    async def test_zero_model_terminal_check_covers_budget_stop_and_retains_failed_artifact(self):
        self.file.write_text('broken=(\n');gate=ArtifactValidation(self.workspace,[self.command]);result=await gate.validate_current();self.assertFalse(result['passed']);self.assertEqual(self.file.read_text(),'broken=(\n');self.assertEqual(len([c for c in self.workspace.commands if c.startswith('set -o pipefail;')]),1)
    async def test_validation_does_not_lease_an_artifact_changed_by_the_validation_command(self):
        command=shlex.quote(sys.executable.replace('\\','/'))+' -c '+shlex.quote("from pathlib import Path;Path('a.py').write_text('answer=2\\n')")
        result=await ArtifactValidation(self.workspace,[command]).validate_current();self.assertFalse(result['passed']);self.assertEqual(result['reason'],'artifact_changed_during_validation')
