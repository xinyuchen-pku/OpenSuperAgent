import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server.app import github_admission, make_server
from server.core import Store
from server.executor import Executor, Provider, Workspace, diff, git
from server.sources import GitHubSource


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'state' / 'test.db')

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self):
        repo = self.root / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
        (repo / 'app.py').write_text('def add(a, b):\n    return a - b\n')
        (repo / '.gitignore').write_text('.env\n')
        git(repo, 'add', '.')
        git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Synthetic fixture')
        return repo


class CoreTests(Fixture):
    def test_explicit_task_records_mandate(self):
        task = self.store.get(self.store.create('Fix add', 'Use addition.'))
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(task['mandate']['basis'], 'explicit')
        self.assertEqual(len(self.store.state()['events']), 1)

    def test_candidate_requires_explicit_approval(self):
        task = self.store.create('Candidate', 'Inspect dependencies.', inferred=True)
        self.assertIsNone(self.store.claim())
        self.store.action(task, 'approve')
        self.assertEqual(self.store.claim(), task)
        self.assertEqual(self.store.get(task)['mandate']['basis'], 'explicit')

    def test_duplicate_trigger_is_durable(self):
        first = self.store.create('First', 'Request.', trigger_id='source:1')
        again = Store(self.store.path).create('Again', 'Request.', trigger_id='source:1')
        self.assertEqual(first, again)
        self.assertEqual(len(self.store.state()['tasks']), 1)

    def test_concurrent_claims_are_unique(self):
        ids = {self.store.create('Task ' + str(i), 'Work.') for i in range(12)}
        with ThreadPoolExecutor(max_workers=6) as workers:
            claimed = list(workers.map(lambda _: self.store.claim(), range(20)))
        self.assertEqual(set(filter(None, claimed)), ids)
        self.assertEqual(len([x for x in claimed if x]), 12)

    def test_pause_prevents_new_dispatch(self):
        task = self.store.create('Task', 'Work.')
        self.store.pause(True)
        self.assertIsNone(self.store.claim())
        self.store.pause(False)
        self.assertEqual(self.store.claim(), task)

    def test_late_result_does_not_resurrect_stopped_task(self):
        task = self.store.create('Task', 'Work.')
        self.store.claim()
        self.store.action(task, 'stop')
        self.store.update(task, status='review', result='A late result.')
        self.assertEqual(self.store.get(task)['status'], 'stopped')

    def test_restart_preserves_and_blocks_interrupted_work(self):
        task = self.store.create('Task', 'Work.')
        self.store.claim()
        self.store.update(task, workspace='/preserved/worktree')
        recovered = Store(self.store.path).get(task)
        self.assertEqual(recovered['status'], 'blocked')
        self.assertEqual(recovered['workspace'], '/preserved/worktree')
        self.store.action(task, 'retry')
        self.assertEqual(self.store.claim(), task)

    def test_invalid_transition_and_input(self):
        task = self.store.create('Task', 'Work.')
        for action in ('complete', 'approve', 'retry', 'invented'):
            with self.assertRaises(ValueError):
                self.store.action(task, action)
        with self.assertRaises(ValueError):
            self.store.create(' ', 'Work.')
        with self.assertRaises(ValueError):
            self.store.pause('false')

    def test_followup_retains_request_and_requeues(self):
        task = self.store.create('Task', 'Original request.')
        self.store.update(task, status='blocked', workspace='/preserved/worktree')
        self.store.followup(task, 'The failure occurs on empty input.')
        current = self.store.get(task)
        self.assertEqual(current['status'], 'queued')
        self.assertIn('Original request.', current['prompt'])
        self.assertIn('empty input', current['prompt'])
        self.assertEqual(current['workspace'], '/preserved/worktree')
        self.store.action(task, 'stop')
        with self.assertRaises(ValueError):
            self.store.followup(task, 'Should stay stopped.')


class WorkspaceTests(Fixture):
    def test_paths_secrets_and_checkpoints_are_blocked(self):
        workspace = Workspace(self.root)
        for name in ('../outside', '/etc/passwd', '.git/config', '.GIT/config', '.env', '.ENV.local', '.env.local', 'keys/private.key', 'weights/model.safetensors', 'optimizer.pt', '.'):
            with self.subTest(path=name), self.assertRaises(ValueError):
                workspace.path(name)

    def test_symlink_file_and_directory_are_blocked(self):
        (self.root / 'target.txt').write_text('Private context.')
        (self.root / 'link.txt').symlink_to(self.root / 'target.txt')
        (self.root / 'alias').symlink_to(self.root, target_is_directory=True)
        for path in ('link.txt', 'alias/target.txt', 'alias/new.txt'):
            with self.assertRaises(ValueError):
                Workspace(self.root).path(path)

    def test_write_and_read_nested_text(self):
        ws = Workspace(self.root)
        ws.call('write_file', {'path': 'src/new.py', 'content': 'print(42)\n'})
        self.assertEqual(ws.call('read_file', {'path': 'src/new.py'}), 'print(42)\n')
        with self.assertRaises(ValueError):
            ws.call('delete_file', {'path': 'src/new.py'})

    def test_limits_protect_existing_file(self):
        ws = Workspace(self.root)
        large = self.root / 'large.txt'
        large.write_text('x' * 65537)
        for method in ('read_file', 'write_file'):
            with self.assertRaises(ValueError):
                ws.call(method, {'path': 'large.txt', 'content': 'replace'})
        self.assertEqual(large.stat().st_size, 65537)
        binary = self.root / 'binary.dat'
        binary.write_bytes(b'abc\x00def')
        with self.assertRaises(ValueError):
            ws.call('write_file', {'path': 'binary.dat', 'content': 'replace'})
        self.assertEqual(binary.read_bytes(), b'abc\x00def')

    def test_diff_includes_untracked_text(self):
        repo = self.repo()
        (repo / 'new.md').write_text('New documentation.\n')
        (repo / '.env').write_text('PRIVATE_TEST=not-a-real-secret')
        output = diff(repo)
        self.assertIn('+++ b/new.md', output)
        self.assertNotIn('PRIVATE_TEST', output)


class ExecutorTests(Fixture):
    def test_real_worktree_and_tool_loop_with_scripted_provider(self):
        repo = self.repo()
        store = self.store
        class ScriptedProvider:
            n = 0
            def complete(self, messages):
                self.n += 1
                if self.n == 1:
                    return {'role': 'assistant', 'content': None, 'reasoning_content': 'test provider context', 'tool_calls': [{'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"app.py"}'}}]}
                if self.n == 2:
                    assert messages[2]['reasoning_content'] == 'test provider context'
                    assert 'return a - b' in messages[3]['content']
                    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'write', 'type': 'function', 'function': {'name': 'write_file', 'arguments': json.dumps({'path': 'app.py', 'content': 'def add(a, b):\n    return a + b\n'})}}]}
                return {'role': 'assistant', 'content': 'Changed subtraction to addition. Tests were not run.'}
        task_id = store.create('Fix add', 'Use addition.')
        store.claim()
        Executor(store, repo, self.root / 'work', ScriptedProvider()).run(task_id)
        task = store.get(task_id)
        self.assertEqual(task['status'], 'review')
        self.assertIn('+    return a + b', task['diff'])
        self.assertIn('return a - b', (repo / 'app.py').read_text())
        self.assertIn('return a + b', (Path(task['workspace']) / 'app.py').read_text())
        self.assertEqual(git(repo, 'status', '--porcelain'), '')

    def test_stop_while_provider_request_is_in_flight(self):
        repo = self.repo()
        store = self.store
        task_id = store.create('Stop test', 'Work.')
        store.claim()
        class StopProvider:
            def complete(self, messages):
                store.action(task_id, 'stop')
                return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'late', 'type': 'function', 'function': {'name': 'write_file', 'arguments': '{"path":"late.txt","content":"never write"}'}}]}
        Executor(store, repo, self.root / 'work', StopProvider()).run(task_id)
        self.assertEqual(store.get(task_id)['status'], 'stopped')
        self.assertFalse((self.root / 'work' / task_id / 'late.txt').exists())

    def test_model_budget_blocks_and_preserves_workspace(self):
        repo = self.repo()
        class Loop:
            def complete(self, messages):
                return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(len(messages)), 'type': 'function', 'function': {'name': 'write_file', 'arguments': '{"path":"partial.md","content":"Partial work before the step budget."}'}}]}
        task = self.store.create('Loop', 'Work.')
        self.store.claim()
        Executor(self.store, repo, self.root / 'work', Loop(), max_steps=2).run(task)
        self.assertEqual(self.store.get(task)['status'], 'blocked')
        self.assertIn('2-step', self.store.get(task)['result'])
        self.assertTrue((self.root / 'work' / task / 'app.py').exists())
        self.assertIn('+++ b/partial.md', self.store.get(task)['diff'])

    def test_missing_configuration_is_actionable(self):
        task = self.store.create('Task', 'Work.')
        self.store.claim()
        Executor(self.store, None, self.root / 'work', None).run(task)
        self.assertIn('OSA_REPO', self.store.get(task)['result'])
        self.assertEqual(self.store.get(task)['status'], 'blocked')

    def test_provider_requires_secure_transport(self):
        for base in ('http://example.com', 'https://user:password@example.com', 'https://example.com?key=abc'):
            with self.assertRaises(ValueError):
                Provider(base, 'test', 'test')
        self.assertEqual(Provider('http://127.0.0.1:1234/v1/', 'test', 'test').url, 'http://127.0.0.1:1234/v1/chat/completions')

    def test_provider_http_protocol_to_real_worktree(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        requests = []
        class ModelHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'file', 'type': 'function', 'function': {'name': 'write_file', 'arguments': '{"path":"guide.md","content":"A real file from a scripted HTTP provider.\\n"}'}}]} if len(requests) == 1 else {'role': 'assistant', 'content': 'Added guide.md. Tests were not run.'}
                data = json.dumps({'choices': [{'finish_reason': 'tool_calls' if len(requests) == 1 else 'stop', 'message': message}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        model = ThreadingHTTPServer(('127.0.0.1', 0), ModelHandler)
        worker = threading.Thread(target=model.serve_forever, daemon=True)
        worker.start()
        try:
            provider = Provider('http://127.0.0.1:' + str(model.server_port) + '/v1', 'synthetic-not-a-real-key', 'scripted-model')
            repo = self.repo()
            task = self.store.create('Add guide', 'Create guide.md.')
            self.store.claim()
            Executor(self.store, repo, self.root / 'work', provider).run(task)
            result = self.store.get(task)
            self.assertEqual(result['status'], 'review')
            self.assertIn('+++ b/guide.md', result['diff'])
            self.assertTrue((Path(result['workspace']) / 'guide.md').is_file())
            self.assertFalse((repo / 'guide.md').exists())
            self.assertEqual(requests[0][0], '/v1/chat/completions')
            self.assertEqual(requests[0][1]['model'], 'scripted-model')
            self.assertEqual(requests[1][1]['messages'][-1]['role'], 'tool')
        finally:
            model.shutdown()
            model.server_close()
            worker.join()


class GitHubTests(Fixture):
    def payload(self, actor='maintainer', body='@opensuperagent fix the bug'):
        return {'action': 'opened', 'repository': {'full_name': 'example/repo'}, 'sender': {'login': actor, 'type': 'User'}, 'issue': {'number': 3, 'title': 'Fix issue', 'body': body}}

    def test_admission_requires_actor_mention_and_repository(self):
        self.assertIsNotNone(github_admission(self.payload(), 'issues', {'maintainer'}, 'example/repo', 'opensuperagent'))
        self.assertIsNone(github_admission(self.payload('stranger'), 'issues', {'maintainer'}, 'example/repo', 'opensuperagent'))
        self.assertIsNone(github_admission(self.payload(body='@opensuperagent-evil do work'), 'issues', {'maintainer'}, 'example/repo', 'opensuperagent'))
        with self.assertRaises(ValueError):
            github_admission(self.payload(), 'issues', {'maintainer'}, 'other/repo', 'opensuperagent')

    def test_polling_observes_labeled_candidates_and_deduplicates(self):
        source = GitHubSource(self.store, 'example/repo', ['maintainer'])
        issues = [{'number': 8, 'title': 'Update docs', 'body': 'Improve docs.', 'updated_at': '2026-11-02T10:00:00Z', 'user': {'login': 'maintainer'}, 'labels': [{'name': 'agent-candidate'}]}]
        source.poll(lambda url: issues)
        source.poll(lambda url: issues)
        tasks = self.store.state()['tasks']
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['status'], 'observed')
        self.assertIsNone(self.store.claim())

    def test_polling_explicit_request_and_actor_filter(self):
        source = GitHubSource(self.store, 'example/repo', ['maintainer'])
        issues = [{'number': i, 'title': 'Issue', 'body': '@opensuperagent fix', 'updated_at': '2026-11-02T10:00:00Z', 'user': {'login': actor}, 'labels': []} for i, actor in [(1, 'maintainer'), (2, 'stranger')]]
        source.poll(lambda url: issues)
        self.assertEqual(len(self.store.state()['tasks']), 1)
        self.assertEqual(self.store.state()['tasks'][0]['status'], 'queued')


class HTTPTests(Fixture):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {'OSA_WEBHOOK_SECRET': 'synthetic-test-secret', 'OSA_GITHUB_REPO': 'example/repo', 'OSA_ALLOWED_ACTORS': 'maintainer', 'OSA_UI_TOKEN': ''})
        self.env.start()
        executor = Executor(self.store, None, self.root / 'work', None)
        self.server = make_server(self.store, executor, self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.env.stop()
        super().tearDown()

    def request(self, route, body=None, headers=None):
        hdr = {'Content-Type': 'application/json', **(headers or {})}
        data = json.dumps(body).encode() if body is not None else None
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(self.url + route, data=data, headers=hdr), timeout=3)

    def test_task_creation_and_scheduler_api(self):
        with self.request('/api/tasks', {'title': 'HTTP task', 'prompt': 'Work.'}) as r:
            self.assertEqual(r.status, 201)
        with self.request('/api/scheduler', {'paused': True}) as r:
            self.assertEqual(r.status, 200)
        with self.request('/api/state') as r:
            state = json.load(r)
        self.assertTrue(state['paused'])
        self.assertEqual(state['tasks'][0]['title'], 'HTTP task')
        self.assertFalse(state['ready'])

    def test_cross_origin_and_rebinding_are_rejected(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.request('/api/tasks', {'title': 'Wrong origin', 'prompt': 'Work.'}, headers)
            self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.store.state()['tasks'], [])

    def test_signed_webhook_durable_replay_and_bad_signature(self):
        body = GitHubTests.payload(self)
        signature = 'sha256=' + hmac.new(b'synthetic-test-secret', json.dumps(body).encode(), hashlib.sha256).hexdigest()
        headers = {'X-Hub-Signature-256': signature, 'X-GitHub-Event': 'issues', 'X-GitHub-Delivery': 'delivery-123'}
        for _ in range(2):
            with self.request('/api/webhooks/github', body, headers) as r:
                self.assertIsNotNone(json.load(r)['task_id'])
        self.assertEqual(len(self.store.state()['tasks']), 1)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('/api/webhooks/github', body, {**headers, 'X-Hub-Signature-256': 'sha256=invalid'})
        self.assertEqual(e.exception.code, 403)


if __name__ == '__main__':
    unittest.main()
