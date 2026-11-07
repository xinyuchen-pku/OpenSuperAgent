from pathlib import Path
import hashlib,json,shlex
from harbor.agents.base import BaseAgent
class FrozenPatchReplayAgent(BaseAgent):
 @staticmethod
 def name():return 'osa-frozen-patch-replay'
 def version(self):return '1'
 def __init__(self,*args,patch_path,patch_sha256,**kwargs):
  super().__init__(*args,**kwargs);self.patch=Path(patch_path);self.patch_sha256=patch_sha256
  assert hashlib.sha256(self.patch.read_bytes()).hexdigest()==self.patch_sha256
 async def setup(self,environment):
  code="from pathlib import Path;import json;p=Path('/sys/fs/cgroup');print(json.dumps({n:(p/n).read_text().strip()for n in ['cpu.max','memory.max']}))";x=await environment.exec(command='python3 -c '+shlex.quote(code),timeout_sec=20);assert x.return_code==0;probe=json.loads(x.stdout);assert probe=={'cpu.max':'100000 100000','memory.max':'4294967296'},probe
  (self.logs_dir/'resource-proof.json').write_text(json.dumps(probe))
 async def run(self,instruction,environment,context):
  assert hashlib.sha256(self.patch.read_bytes()).hexdigest()==self.patch_sha256
  await environment.upload_file(source_path=self.patch,target_path='/tmp/osa-frozen-model.patch')
  command="if test -d /app/.git;then cd /app;elif test -d /testbed/.git;then cd /testbed;else exit 2;fi; if test -s /tmp/osa-frozen-model.patch;then git apply --verbose /tmp/osa-frozen-model.patch || git apply --3way /tmp/osa-frozen-model.patch || patch --fuzz=3 -p1 -i /tmp/osa-frozen-model.patch;else printf 'Empty frozen model patch\\n';fi"
  x=await environment.exec(command=command,timeout_sec=300);(self.logs_dir/'patch-replay.json').write_text(json.dumps({'patch_sha256':self.patch_sha256,'bytes':self.patch.stat().st_size,'returncode':x.return_code,'stdout':x.stdout,'stderr':x.stderr,'scope':'Apply frozen model artifact only; original task/verifier unchanged; no inference calls'}))
