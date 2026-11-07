"""Deterministic role writes over the original native task workspace.

Shell tools see a live read-only /workspace in a separate network namespace.
The original SDK remains the only writer, through an exact-path edit operation.
No foreign change is removed to manufacture a compliant benchmark artifact.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import threading
import time

from .contracts import canonical, digest
from .kernel import function_tool


_LOCK = threading.RLock()
_RESOURCES = {}


class ScopedAsynWorkspace:
    cleanup_grace_s = 6

    def __init__(self, inner, *, container_id, allowed_paths, docker_prefix, output, assignment,
                 expected_image):
        self.inner, self.sdk_container = inner, container_id
        self.allowed = tuple(sorted(set(allowed_paths)))
        if not self.allowed:
            raise ValueError('Native role requires explicit original writable paths')
        for path in self.allowed:
            p = PurePosixPath(path)
            if p.is_absolute() or '..' in p.parts or str(p) != path or '\\' in path:
                raise ValueError('Writable scope must use exact repository-relative files')
        self.prefix, self.output = list(docker_prefix), Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.assignment, self.expected_image = assignment, expected_image
        self.root = inner.path
        if not self.root.startswith('/workspace/'):
            raise ValueError('This pinned Docker adapter requires its native /workspace path')
        self.container = None
        self.resource = None
        self.base = None
        self.identity = dict(inner.identity, scope_enforcement='readonly-live-workspace+exact-edit',
                             original_writable_paths=list(self.allowed))
        execute = function_tool('execute', 'Read repository files, run tests, and install dependencies. '
            '/workspace is read-only. Use edit_file for source edits; put scratch files in /tmp. '
            'The caller creates the implementation commit after execution.', {'command': {'type':'string'}})
        edit = function_tool('edit_file', 'Replace exactly one matching text block in an authorized file. '
            'Ambiguous/missing text is rejected without changing the file. Empty old_text only creates '
            'an absent or empty authorized file.', {'path': {'type':'string','enum':list(self.allowed)},
                'old_text':{'type':'string'}, 'new_text':{'type':'string'}})
        self.model_tools = [execute, edit]

    def _docker(self, args, timeout=120):
        p = subprocess.run([*self.prefix, *args], capture_output=True, text=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError('Owned scope runtime operation failed: '+p.stderr[-1800:])
        return p.stdout.strip()

    def _event(self, kind, **data):
        with (self.output/'events.jsonl').open('a',encoding='utf-8') as f:
            f.write(canonical({'at':time.time(),'kind':kind,**data})+'\n')

    async def prepare(self):
        probe = await self.inner.execute('python -I -c '+shlex.quote(
            "import os,sys,json;print(json.dumps({'python':sys.executable,'env':{k:v for k,v in os.environ.items() "
            "if k in ['PATH','PYTHONPATH','VIRTUAL_ENV','LANG','LC_ALL','TZ','LD_LIBRARY_PATH'] or k.startswith('PIP_')}}))"),30)
        if probe['returncode']:
            raise RuntimeError('Original native execution environment could not be read')
        self.original_env = json.loads(probe['stdout'])
        base = await self.inner.execute('git rev-parse --verify HEAD',20)
        self.base = base['stdout'].strip()
        if base['returncode'] or len(self.base)!=40:
            raise RuntimeError('Native artifact baseline missing')
        await asyncio.to_thread(self._prepare_sync)

    def _prepare_sync(self):
        with _LOCK:
            info=json.loads(self._docker(['inspect',self.sdk_container]))[0]
            if (info['Id']!=self.sdk_container or info['Image']!=self.expected_image
                    or not info['State']['Running'] or info['Mounts']):
                raise ValueError('Native SDK container identity/mount contract changed')
            resource=_RESOURCES.get(self.sdk_container)
            if resource is None:
                merged=info['GraphDriver']['Data'].get('MergedDir')
                if not merged or not merged.startswith('/'):
                    raise RuntimeError('Live read-only bind requires the admitted Docker overlay backend')
                tag='osa-scope:'+self.sdk_container[:16]
                network='osa-scope-'+self.sdk_container[:16]
                started=time.time()
                network_id=self._docker(['network','create','--driver','bridge',network])
                image_id=self._docker(['commit',self.sdk_container,tag])
                resource={'SDK_container':self.sdk_container,'SDK_image':self.expected_image,
                    'execution_image':image_id,'image_tag':tag,'network':network,'network_id':network_id,
                    'workspace_bind_source':merged+'/workspace','refs':0,'setup_s':time.time()-started}
                _RESOURCES[self.sdk_container]=resource
            name='osa-scope-'+digest([self.sdk_container,self.assignment,str(self.output)])[:20]
            args=['run','-d','--name',name,'--network',resource['network'],'--cap-drop','ALL',
                '--security-opt','no-new-privileges','--label','osa.scope.assignment='+self.assignment,
                '--mount','type=bind,src='+resource['workspace_bind_source']+',dst=/workspace,readonly']
            for key,value in self.original_env['env'].items():
                args+=['--env',key+'='+value]
            args+=['--entrypoint',self.original_env['python'],resource['execution_image'],
                   '-I','-c','import time;time.sleep(14400)']
            self.container=self._docker(args)
            spec=json.loads(self._docker(['inspect',self.container]))[0]
            if not (spec['Image']==resource['execution_image'] and len(spec['Mounts'])==1
                    and not spec['Mounts'][0]['RW'] and spec['HostConfig']['NetworkMode']==resource['network']):
                raise RuntimeError('Scope execution container admission failed')
            resource['refs']+=1
            self.resource=resource
            self.identity.update(execution_container=self.container,execution_image=resource['execution_image'],
                SDK_container=self.sdk_container,SDK_image=self.expected_image,readonly_workspace=True,
                separate_network=resource['network'],native_resource_pool='Original local VM4CPU16GiB; no per-role quota override')
            (self.output/'runtime.json').write_text(canonical({'identity':self.identity,'resource':resource,
                'base_ref':self.base,'tools_sha256':digest(self.model_tools)}),encoding='utf-8')

    async def execute(self, command, timeout_s):
        if self.container is None:
            raise RuntimeError('Scope runtime is not prepared')
        cache='/tmp/osa-scope-'+digest(self.assignment)[:12]
        args=[*self.prefix,'exec','-w',self.root,'--env','PYTHONPYCACHEPREFIX='+cache+'/pycache',
            '--env','PYTEST_ADDOPTS=-o cache_dir='+cache+'/pytest','--env','GIT_OPTIONAL_LOCKS=0',
            self.container,'timeout','--signal=TERM','--kill-after=5',str(timeout_s),'bash','-c',command]
        started=time.time();p=await asyncio.create_subprocess_exec(*args,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:stdout,stderr=await asyncio.wait_for(p.communicate(),timeout_s+15)
        except BaseException:
            if p.returncode is None:p.kill();await p.wait()
            self._event('execution_outcome_uncertain',command=command)
            raise
        result={'returncode':p.returncode,'stdout':stdout.decode('utf-8',errors='replace'),
                'stderr':stderr.decode('utf-8',errors='replace')}
        self._event('readonly_execute',command=command,elapsed_s=time.time()-started,**result)
        return result

    async def edit_file(self, path, old_text, new_text, timeout_s):
        if path not in self.allowed:
            result={'returncode':13,'stdout':'','stderr':'Path is outside the original benchmark role scope.',
                    'scope_write_denied':True,'allowed_paths':list(self.allowed)}
            self._event('edit_rejected',path=path,**result)
            return result
        data={'root':self.root,'path':path,'old':old_text,'new':new_text,'allowed':self.allowed}
        code=r'''import json,base64,os,tempfile,hashlib,difflib
from pathlib import Path
d=json.loads(base64.b64decode(PAYLOAD));root=Path(d['root']).resolve();p=root/d['path']
assert d['path'] in d['allowed'] and p.resolve().is_relative_to(root)
assert not any(x.is_symlink() for x in [p,*p.parents] if x!=root and x.is_relative_to(root))
before=p.read_bytes() if p.exists() else b'';text=before.decode('utf-8');old=d['old'];count=text.count(old) if old else (1 if not text else 0)
if count!=1:
 print(json.dumps({'reason':'old_text_not_unique','matches':count,'changed':False}));raise SystemExit(2)
after=(text.replace(old,d['new'],1) if old else d['new']).encode('utf-8');mode=p.stat().st_mode&0o777 if p.exists() else 0o644
fd,name=tempfile.mkstemp(prefix='.osa-edit-',dir=p.parent)
try:
 with os.fdopen(fd,'wb')as f:f.write(after)
 os.chmod(name,mode);os.replace(name,p)
finally:
 if os.path.exists(name):os.unlink(name)
print(json.dumps({'path':d['path'],'changed':before!=after,'before_sha256':hashlib.sha256(before).hexdigest(),
 'after_sha256':hashlib.sha256(after).hexdigest(),'diff':''.join(difflib.unified_diff(text.splitlines(True),after.decode().splitlines(True),fromfile='a/'+d['path'],tofile='b/'+d['path']))}))
'''.replace('PAYLOAD',repr(base64.b64encode(canonical(data).encode()).decode()))
        result=await self.inner.execute(self.original_env['python']+' -I -c '+shlex.quote(code),timeout_s)
        self._event('scoped_edit',path=path,result=result)
        return result

    async def finalize(self):
        # Observe every artifact terminal path, including budget/step stops. Never sanitize it.
        payload={'base':self.base,'allowed':self.allowed}
        code=r'''import subprocess,json,base64
d=json.loads(base64.b64decode(PAYLOAD));git=lambda args:subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*args])
a=git(['diff','--no-ext-diff','--no-textconv','--name-only','-z',d['base'],'--']);b=git(['ls-files','--others','--exclude-standard','-z'])
paths=sorted(set(x.decode()for x in(a+b).split(bytes([0]))if x));outside=[p for p in paths if p not in d['allowed']]
report={'changed_paths':paths,'out_of_scope_paths':outside,'scope_passed':not outside,'commit':None,'foreign_changes_deleted':False}
if outside or not paths:
 report['reason']='out_of_scope_artifact'if outside else'no_source_changes';print(json.dumps(report));raise SystemExit(3)
staged=git(['diff','--cached','--name-only','-z']).decode().split(chr(0));assert all(not p or p in d['allowed']for p in staged)
git(['add','--',*paths]);git(['-c','user.name=OpenSuperAgent Worker','-c','user.email=worker@example.invalid','commit','-m','Implement assigned native role'])
report.update(commit=git(['rev-parse','HEAD']).decode().strip(),reason='allowed_artifact_committed');print(json.dumps(report))
'''.replace('PAYLOAD',repr(base64.b64encode(canonical(payload).encode()).decode()))
        result=await self.inner.execute(self.original_env['python']+' -I -c '+shlex.quote(code),90)
        self._event('artifact_handoff',result=result)
        return result

    async def close(self):
        if not self.container:return
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self):
        with _LOCK:
            info=json.loads(self._docker(['inspect',self.container]))[0]
            if (info['Id']!=self.container or info['Image']!=self.resource['execution_image'] or
                info['Config']['Labels'].get('osa.scope.assignment')!=self.assignment):
                raise RuntimeError('Scope runtime ownership changed; cleanup refused')
            self._docker(['stop','--time','10',self.container]);self._event('scope_runtime_stopped',container=self.container)
            self.resource['refs']-=1
            # Keep immutable image/container records for audit; original SDK lifecycle belongs to its harness.
            self.container=None
