"""Resource probes must fail closed and stop their own rejected workspace."""
import json
import subprocess
import unittest
from unittest.mock import patch

from osa_eval.workspace import DockerWorkspace


class ResourceContractTests(unittest.TestCase):
    def create(self, probe):
        info = {'Id': 'owned-container', 'Image': 'sha256:fixed',
                'HostConfig': {'NetworkMode': 'none'}}
        commands = []

        def run(argv, **kwargs):
            commands.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout='owned-container\n', stderr='')

        with patch('osa_eval.workspace.subprocess.run', side_effect=run), patch(
                'osa_eval.workspace.subprocess.check_output',
                side_effect=[json.dumps([info]), probe]):
            try:
                return DockerWorkspace.create(image='sha256:fixed', name='own-test',
                    purpose='agent', cpus=1, memory_mb=4096), commands
            except BaseException:
                self.assertEqual(commands[-1], ['docker', 'stop', '--time', '15', 'owned-container'])
                raise

    def test_actual_matching_limits_are_recorded(self):
        workspace, commands = self.create(json.dumps({'memory.max': '4294967296', 'cpu.max': '100000 100000'}))
        self.assertTrue(workspace.identity['cgroup_limits_enforced'])
        self.assertEqual(len(commands), 1)

    def test_unlimited_or_different_resources_are_rejected(self):
        for probe in [{'memory.max': 'max', 'cpu.max': 'max 100000'},
                      {'memory.max': '2147483648', 'cpu.max': '100000 100000'}]:
            with self.subTest(probe=probe), self.assertRaisesRegex(RuntimeError, 'CPU/RAM'):
                self.create(json.dumps(probe))

    def test_probe_failure_stops_only_created_container(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.create(subprocess.CalledProcessError(1, 'resource-probe'))

    def test_remote_prefix_is_retained_for_stop(self):
        prefix = ['docker', '--host', 'tcp://fixed-host:2376', '--tlsverify']
        workspace = DockerWorkspace('owned-container', '/app', image_digest='sha256:fixed', command_prefix=prefix)
        with patch('osa_eval.workspace.subprocess.run') as run:
            workspace.stop()
        self.assertEqual(run.call_args.args[0], [*prefix, 'stop', '--time', '15', 'owned-container'])
