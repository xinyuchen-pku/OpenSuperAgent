"""One current-artifact check at handoff, including budget and step-limit exits.

This gate certifies only its explicit public checks. Official benchmark scoring
is independent. No extra model turn or completion-reflection loop is requested.
"""
from __future__ import annotations
import base64
import json
import shlex
import time
from .contracts import canonical,digest


class ArtifactValidation:
    def __init__(self,workspace,commands,*,timeout_s=240):
        if not commands or any(not isinstance(c,str)or not c.strip()for c in commands):
            raise ValueError('Explicit public validation commands are required')
        self.workspace,self.commands,self.timeout_s=workspace,list(commands),timeout_s
        self.base=None;self.current=None;self.revision=0;self.validated_revision=None

    async def fingerprint(self):
        if self.base is None:
            r=await self.workspace.execute('git rev-parse --verify HEAD',20)
            if r['returncode']:raise RuntimeError('Artifact baseline missing')
            self.base=r['stdout'].strip()
        code=r'''import subprocess,os,json,hashlib,stat
from pathlib import Path
base=BASE;env=dict(os.environ,GIT_OPTIONAL_LOCKS='0');git=lambda a:subprocess.check_output(['git','-c','core.fsmonitor=false',*a],env=env)
patch=git(['diff','--binary','--no-ext-diff','--no-textconv',base,'--']);paths=[p.decode()for p in git(['ls-files','--others','--exclude-standard','-z']).split(bytes([0]))if p]
other=[]
for name in sorted(paths):
 p=Path(name);s=p.lstat();data=os.readlink(p).encode()if p.is_symlink()else p.read_bytes();other.append([name,s.st_mode&0o777,hashlib.sha256(data).hexdigest()])
payload=json.dumps({'base':base,'tracked_patch_sha256':hashlib.sha256(patch).hexdigest(),'untracked':other},sort_keys=True,separators=(',',':')).encode();print(json.dumps({'fingerprint':hashlib.sha256(payload).hexdigest(),'untracked_paths':paths}))
'''.replace('BASE',repr(self.base))
        r=await self.workspace.execute('python3 -I -c '+shlex.quote(code),40)
        if r['returncode']:raise RuntimeError('Artifact fingerprint unavailable')
        return json.loads(r['stdout'])['fingerprint']

    def observe(self,fingerprint):
        if self.current!=fingerprint:
            self.revision+=1;self.current=fingerprint;self.validated_revision=None

    async def validate_current(self):
        started=time.monotonic();before=await self.fingerprint();self.observe(before)
        command='set -o pipefail; '+' && '.join('('+c+')'for c in self.commands)
        result=await self.workspace.execute(command,self.timeout_s);after=await self.fingerprint()
        if after!=before:self.observe(after)
        passed=result['returncode']==0 and before==after
        if passed:self.validated_revision=self.revision
        return {'passed':passed,'validation_current':self.validated_revision==self.revision,
            'before_fingerprint':before,'after_fingerprint':after,'artifact_revision':self.revision,
            'commands':self.commands,'checks':result,'elapsed_s':time.monotonic()-started,
            'benchmark_success_claimed':False,'scope':'Only the declared public checks on the current artifact',
            'reason':'public_checks_passed'if passed else('artifact_changed_during_validation'if before!=after else'public_checks_failed')}
