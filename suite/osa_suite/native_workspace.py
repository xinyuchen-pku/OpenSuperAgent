"""Private role reads over the frozen source025 exact-path edit/handoff tools.

The legacy read-only /workspace bind contained all sibling worktrees. Keep the
SDK as the writer but mount only the assigned tree into the shell container.
An isolated shallow Git snapshot supplies the same base/index for git diff.
"""
from __future__ import annotations

import json
import re
import shlex
import time
import uuid
from pathlib import PurePosixPath

from osa_eval.contracts import canonical, digest
from osa_eval.scoped_workspace import ScopedAsynWorkspace, _LOCK, _RESOURCES


def role_path(value):
    parts = PurePosixPath(value).parts
    if len(parts) < 3 or parts[:2] != ('/', 'workspace') or str(PurePosixPath(value)) != value:
        raise ValueError('Expected normalized native private worktree path')
    if any(part in ('.', '..') or not re.fullmatch(r'[a-zA-Z0-9_.-]+', part) for part in parts[2:]):
        raise ValueError('Unsafe private worktree path component')
    return value


class PrivateReadWorkspace(ScopedAsynWorkspace):
    async def prepare(self):
        path = role_path(self.root)
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
        check = ('set -eu; test "$(git rev-parse HEAD)" = ' + shlex.quote(self.base) + '; '
            'test "$(git rev-list --all --count)" = 1; '
            'git -c core.fsmonitor=false status --porcelain >/dev/null; '
            'python -I -c ' + shlex.quote(
                'from pathlib import Path; p=Path.cwd(); assert str(p)==' + repr(self.root) + '; '
                'assert set(p.parent.iterdir())=={p}'))
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
                not info['State']['Running'] or info['Mounts']):
                raise ValueError('Native SDK container identity/mount contract changed')
            resource = _RESOURCES.get(self.sdk_container)
            if resource is None:
                merged = info['GraphDriver']['Data'].get('MergedDir')
                if not merged or not merged.startswith('/') or ',' in merged:
                    raise ValueError('Private role mount requires admitted Docker overlay backend')
                tag = 'osa-s2-private:' + self.sdk_container[:16]
                net = 'osa-s2-private-' + self.sdk_container[:16]
                start = time.time()
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
            for key, value in self.original_env['env'].items():
                args += ['--env', key + '=' + value]
            args += ['--env', 'GIT_DIR=/osa_role_git', '--env', 'GIT_WORK_TREE=' + self.root,
                     '--entrypoint', self.original_env['python'], resource['execution_image'],
                     '-I', '-c', 'import time;time.sleep(14400)']
            self.container = self._docker(args)
            resource['refs'] += 1
            spec = json.loads(self._docker(['inspect', self.container]))[0]
            mounts = {m['Destination']: m['Source'] for m in spec['Mounts'] if m['Type'] == 'bind' and not m['RW']}
            if (spec['Image'] != resource['execution_image'] or mounts != paths or len(spec['Mounts']) != 2 or
                spec['HostConfig'].get('Privileged') is True or
                '/workspace' not in (spec['HostConfig'].get('Tmpfs') or {}) or
                spec['HostConfig']['NetworkMode'] != resource['network']):
                raise RuntimeError('Native private-read mount contract not enforced')
            self.identity.update(execution_container=self.container, execution_image=resource['execution_image'],
                SDK_container=self.sdk_container, SDK_image=self.expected_image, readonly_workspace=True,
                private_role_read=True, visible_workspace=self.root, separate_network=resource['network'],
                native_resource_pool='Original local VM4CPU16GiB; no per-role quota override')
            (self.output / 'runtime.json').write_text(canonical(dict(identity=self.identity, resource=resource,
                base_ref=self.base, tools_sha256=digest(self.model_tools))), encoding='utf-8')
