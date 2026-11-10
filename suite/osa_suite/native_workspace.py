"""Private role reads over the frozen source025 exact-path edit/handoff tools.

The legacy read-only /workspace bind contained all sibling worktrees. Keep the
SDK as the writer but mount only the assigned tree into the shell container.
An isolated shallow Git snapshot supplies the same base/index for git diff.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import PurePosixPath

from osa_eval.contracts import canonical, digest
from osa_eval.scoped_workspace import ScopedAsynWorkspace, _LOCK, _RESOURCES


PR_HARD_CPU_LIMIT = 28
_PR_HARD_CACHE_ROOT = PurePosixPath('/workspace/.asyncodebench-pr-hard-build-cache')


def native_task_id(value):
    if re.fullmatch(r'pr-hard:apache-tvm-\d+', value):
        return value.replace('pr-hard:', 'asyncodebench:', 1)
    return value


def role_path(value):
    parts = PurePosixPath(value).parts
    if len(parts) < 3 or parts[:2] != ('/', 'workspace') or str(PurePosixPath(value)) != value:
        raise ValueError('Expected normalized native private worktree path')
    if any(part in ('.', '..') or not re.fullmatch(r'[a-zA-Z0-9_.-]+', part) for part in parts[2:]):
        raise ValueError('Unsafe private worktree path component')
    return value


def role_build_cache(path):
    name = PurePosixPath(role_path(path)).name.strip('-.') or 'workspace'
    suffix = hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]
    return str(_PR_HARD_CACHE_ROOT / f'{name}-{suffix}')


def pr_hard_cache_source(info, target):
    mounts = info['Mounts']
    cpu_limit = info['HostConfig'].get('NanoCpus')
    if len(mounts) != 1 or cpu_limit != PR_HARD_CPU_LIMIT * 10**9:
        raise ValueError('PR-hard requires its original cache bind and 28-CPU SDK quota')
    mount = mounts[0]
    source = mount['Source']
    if (mount['Type'] != 'bind' or not mount['RW'] or mount['Destination'] != str(_PR_HARD_CACHE_ROOT)
            or not re.fullmatch(r'(/[a-zA-Z0-9_.-]+)+', source)
            or any(part in ('.', '..') for part in PurePosixPath(source).parts)):
        raise ValueError('Unexpected PR-hard build cache mount')
    return source + '/' + PurePosixPath(target).name


class PrivateReadWorkspace(ScopedAsynWorkspace):
    def __init__(self, inner, *, offline_guard=None, **kwargs):
        super().__init__(inner, **kwargs)
        self.offline_guard = offline_guard
        self.build_cache = role_build_cache(self.root) if offline_guard else None
        if offline_guard:
            self.model_tools[0]['function']['description'] = (
                'Read repository files and run local builds or tests offline. '
                'Use edit_file for source edits and /tmp for scratch files. '
                'The build directory is reserved for this role’s build outputs.')

    async def execute(self, command, timeout_s):
        if self.offline_guard:
            event = json.dumps(dict(tool_name='terminal', tool_input={'command': command}))
            completed = await asyncio.to_thread(
                subprocess.run, [sys.executable, *self.offline_guard[1:]], input=event,
                capture_output=True, text=True, timeout=10, check=True)
            decision = json.loads(completed.stdout)
            if decision['decision'] != 'allow':
                result = dict(returncode=13, stdout='', stderr=decision['reason'])
                self._event('offline_command_rejected', command=command, **result)
                return result
        return await super().execute(command, timeout_s)

    async def prepare(self):
        path = role_path(self.root)
        if self.build_cache:
            target = shlex.quote(self.build_cache)
            probe = await self.inner.execute(
                f'test -L build && test "$(readlink build)" = {target} '
                f'&& test "$(readlink -f build)" = {target} && test -d {target}', 30)
            if probe['returncode']:
                raise RuntimeError('PR-hard worktree is missing its original private build cache')
        self.git_snapshot = '/tmp/osa-s2-git-' + uuid.uuid4().hex
        command = ('set -eu; ' + 'g=' + shlex.quote(self.git_snapshot) + '; ' +
            'git -c protocol.file.allow=always clone --bare --no-local --depth=1 --single-branch --no-tags ' +
            shlex.quote('file://' + path) + ' "$g"; '
            'test "$(git --git-dir "$g" rev-parse HEAD)" = "$(git rev-parse HEAD)"; '
            'test "$(git --git-dir "$g" rev-list --all --count)" = 1; '
            'git --git-dir "$g" read-tree HEAD; git --git-dir "$g" config core.bare false; '
            'git --git-dir "$g" config --remove-section remote.origin || true')
        proof = await self.inner.execute(command, 300)
        if proof['returncode']:
            raise RuntimeError('Unable to isolate the role Git baseline: ' + proof['stderr'][-1500:])
        await super().prepare()
        visible = [path]
        if self.build_cache and PurePosixPath(path).parent == _PR_HARD_CACHE_ROOT.parent:
            visible.append(str(_PR_HARD_CACHE_ROOT))
        check = ('set -eu; test "$(git rev-parse HEAD)" = ' + shlex.quote(self.base) + '; '
            'test "$(git rev-list --all --count)" = 1; '
            'git -c core.fsmonitor=false status --porcelain >/dev/null; '
            'python -I -c ' + shlex.quote(
                'from pathlib import Path; p=Path.cwd(); assert str(p)==' + repr(self.root) + '; '
                'assert set(map(str, p.parent.iterdir()))==set(' + repr(visible) + ')'))
        if self.build_cache:
            check += ('; test "$(readlink -f build)" = ' + shlex.quote(self.build_cache)
                      + '; test -w build; test "$(ls -A ' + shlex.quote(str(_PR_HARD_CACHE_ROOT))
                      + ')" = ' + shlex.quote(PurePosixPath(self.build_cache).name))
        checked = await self.execute(check, 60)
        if checked['returncode']:
            raise RuntimeError('Actual private worktree/Git read probe failed')
        self.identity['private_read_preflight'] = True
        (self.output / 'private-read-proof.json').write_text(canonical(dict(
            role_path=self.root, git_base=self.base, git_visible_commits=1, observed_probe=checked,
            identity=self.identity)), encoding='utf-8')

    def _prepare_sync(self):
        with _LOCK:
            info = json.loads(self._docker(['inspect', self.sdk_container]))[0]
            if (info['Id'] != self.sdk_container or info['Image'] != self.expected_image or
                not info['State']['Running']):
                raise ValueError('Native SDK container identity/mount contract changed')
            if info['Mounts'] and not self.build_cache:
                raise ValueError('Unexpected mounts on Commit0 SDK container')
            cache_source = pr_hard_cache_source(info, self.build_cache) if self.build_cache else None
            resource = _RESOURCES.get(self.sdk_container)
            if resource is None:
                merged = info['GraphDriver']['Data'].get('MergedDir')
                if not merged or not merged.startswith('/') or ',' in merged:
                    raise ValueError('Private role mount requires admitted Docker overlay backend')
                tag = 'osa-s2-private:' + self.sdk_container[:16]
                start = time.time()
                if self.build_cache:
                    net, netid = 'none', None
                else:
                    net = 'osa-s2-private-' + self.sdk_container[:16]
                    netid = self._docker(['network', 'create', '--driver', 'bridge', net])
                execution_image = self._docker(['commit', self.sdk_container, tag])
                resource = dict(mode='stage2-private-read', SDK_container=self.sdk_container,
                    SDK_image=self.expected_image, execution_image=execution_image, image_tag=tag,
                    network=net, network_id=netid, merged_dir=merged, refs=0, setup_s=time.time() - start)
                _RESOURCES[self.sdk_container] = resource
            if resource.get('mode') != 'stage2-private-read':
                raise RuntimeError('Legacy broad workspace bind is not admitted')
            self.resource = resource
            name = 'osa-s2-role-' + digest([self.sdk_container, self.assignment, str(self.output)])[:20]
            paths = {self.root: resource['merged_dir'] + self.root,
                     '/osa_role_git': resource['merged_dir'] + self.git_snapshot}
            args = ['run', '-d', '--name', name, '--network', resource['network'], '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges', '--label', 'osa.scope.assignment=' + self.assignment,
                    '--tmpfs', '/workspace:rw,nosuid,nodev']
            for dst, src in paths.items():
                args += ['--mount', 'type=bind,src=' + src + ',dst=' + dst + ',readonly']
            if self.build_cache:
                args += ['--cpus', str(PR_HARD_CPU_LIMIT), '--mount',
                         'type=bind,src=' + cache_source + ',dst=' + self.build_cache
                         + ',bind-recursive=disabled']
            for key, value in self.original_env['env'].items():
                args += ['--env', key + '=' + value]
            args += ['--env', 'GIT_DIR=/osa_role_git', '--env', 'GIT_WORK_TREE=' + self.root,
                     '--entrypoint', self.original_env['python'], resource['execution_image'],
                     '-I', '-c', 'import time;time.sleep(14400)']
            self.container = self._docker(args)
            resource['refs'] += 1
            spec = json.loads(self._docker(['inspect', self.container]))[0]
            expected = {(dst, src, False) for dst, src in paths.items()}
            if self.build_cache:
                expected.add((self.build_cache, cache_source, True))
            mounts = {(m['Destination'], m['Source'], m['RW']) for m in spec['Mounts'] if m['Type'] == 'bind'}
            if (spec['Image'] != resource['execution_image'] or mounts != expected
                or len(spec['Mounts']) != len(expected) or
                spec['HostConfig'].get('Privileged') is True or
                '/workspace' not in (spec['HostConfig'].get('Tmpfs') or {}) or
                spec['HostConfig']['NetworkMode'] != resource['network']):
                raise RuntimeError('Native private-read mount contract not enforced')
            if self.build_cache and (resource['network'] != 'none'
                                     or spec['HostConfig']['NanoCpus'] != PR_HARD_CPU_LIMIT * 10**9):
                raise RuntimeError('PR-hard CPU or offline constraint not enforced')
            self.identity.update(execution_container=self.container, execution_image=resource['execution_image'],
                SDK_container=self.sdk_container, SDK_image=self.expected_image, readonly_workspace=True,
                private_role_read=True, visible_workspace=self.root, separate_network=resource['network'],
                offline_agent=self.build_cache is not None, private_build_cache=self.build_cache,
                role_cpu_quota=PR_HARD_CPU_LIMIT if self.build_cache else None)
            (self.output / 'runtime.json').write_text(canonical(dict(identity=self.identity, resource=resource,
                base_ref=self.base, tools_sha256=digest(self.model_tools))), encoding='utf-8')
