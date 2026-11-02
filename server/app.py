"""Loopback HTTP API, signed GitHub admission, and bounded worker scheduler."""
import argparse
import hashlib
import hmac
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import Store
from .executor import Executor, Provider
from .sources import GitHubSource


def github_admission(payload, event, allowed, repository, bot):
    if payload.get('repository', {}).get('full_name') != repository:
        raise ValueError('Repository is outside configured scope.')
    obj = payload.get('comment') if event == 'issue_comment' else payload.get('issue')
    if event not in ('issues', 'issue_comment') or payload.get('action') not in ('opened', 'created') or not isinstance(obj, dict):
        return None
    actor = payload.get('sender', {})
    body = obj.get('body') or ''
    import re
    if actor.get('type') == 'Bot' or actor.get('login') not in allowed or not re.search(r'(?<![\w-])@' + re.escape(bot) + r'(?![\w-])', body, re.I):
        return None
    issue = payload.get('issue', {})
    return {'title': str(issue.get('title', 'GitHub request'))[:160], 'prompt': body,
            'source': 'github', 'actor': actor['login']}


def make_server(store, executor, static_dir, port=8765):
    root = Path(static_dir).resolve()
    token = os.environ.get('OSA_UI_TOKEN', '')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Never log headers, bodies, credentials or prompt text.

        def respond(self, value, code=200):
            data = json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            host = self.headers.get('Host', '')
            if host not in ('127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)):
                return False
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != host:
                return False
            return not token or hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

        def do_GET(self):
            if not self.authorized():
                return self.respond({'error': 'Local origin or bearer token required.'}, 403)
            if self.path == '/api/state':
                state = store.state()
                state.update(mode='live', repository=os.environ.get('OSA_GITHUB_REPO', executor.repo.name if executor.repo else 'Unconfigured repository'),
                             model=os.environ.get('OSA_MODEL', 'deepseek-flash'), ready=bool(executor.repo and executor.provider), max_steps=executor.max_steps)
                return self.respond(state)
            path = (root / self.path.split('?')[0].lstrip('/')).resolve()
            if path != root and root not in path.parents:
                return self.respond({'error': 'Invalid path.'}, 404)
            if not path.is_file():
                path = root / 'index.html'
            if not path.exists():
                return self.respond({'error': 'Build the web console with pnpm build first.'}, 404)
            import mimetypes
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1000000:
                    return self.respond({'error': 'Body must contain 1–1,000,000 bytes.'}, 413)
                raw = self.rfile.read(length)
                if self.path == '/api/webhooks/github':
                    secret = os.environ.get('OSA_WEBHOOK_SECRET', '')
                    signature = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
                    if not secret or not hmac.compare_digest(signature, self.headers.get('X-Hub-Signature-256', '')):
                        return self.respond({'error': 'Invalid webhook signature.'}, 403)
                    payload = json.loads(raw)
                    delivery = self.headers.get('X-GitHub-Delivery', '')
                    if not delivery or len(delivery) > 200:
                        raise ValueError('GitHub delivery ID required.')
                    accepted = github_admission(payload, self.headers.get('X-GitHub-Event'), set(os.environ.get('OSA_ALLOWED_ACTORS', '').split(',')), os.environ.get('OSA_GITHUB_REPO', ''), os.environ.get('OSA_BOT_MENTION', 'opensuperagent'))
                    issue_number = payload.get('issue', {}).get('number')
                    trigger_id = 'github-issue:' + os.environ.get('OSA_GITHUB_REPO', '') + ':' + str(issue_number) if self.headers.get('X-GitHub-Event') == 'issues' else 'github:' + delivery
                    return self.respond({'task_id': store.create(**accepted, trigger_id=trigger_id) if accepted else None})
                if not self.authorized():
                    return self.respond({'error': 'Local origin or bearer token required.'}, 403)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.respond({'error': 'Use application/json.'}, 415)
                body = json.loads(raw)
                if self.path == '/api/tasks':
                    return self.respond({'task_id': store.create(body.get('title'), body.get('prompt'))}, 201)
                if self.path == '/api/scheduler':
                    store.pause(body.get('paused'))
                elif self.path.startswith('/api/tasks/'):
                    task_id = self.path.rsplit('/', 1)[-1]
                    if body.get('action') == 'followup':
                        store.followup(task_id, body.get('content'))
                    else:
                        store.action(task_id, body.get('action'))
                else:
                    return self.respond({'error': 'Route does not exist.'}, 404)
                self.respond({'ok': True})
            except (ValueError, TypeError, AttributeError) as e:
                self.respond({'error': str(e)}, 400)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='OpenSuperAgent local runtime')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', default='.superagent')
    args = parser.parse_args()
    state = Path(args.state_dir).resolve()
    state.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock = (state / 'runtime.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('Another runtime owns this state directory. Use a different --state-dir.')
    store = Store(state / 'state.sqlite3')
    key = os.environ.get('OSA_API_KEY', '')
    provider = Provider(os.environ.get('OSA_BASE_URL', 'https://api.deepseek.com'), key, os.environ.get('OSA_MODEL', 'deepseek-flash')) if key else None
    executor = Executor(store, os.environ.get('OSA_REPO'), state / 'work', provider, max_steps=20)
    source = GitHubSource(store, os.environ.get('OSA_GITHUB_REPO', ''), filter(None, os.environ.get('OSA_ALLOWED_ACTORS', '').split(',')),
                          os.environ.get('OSA_BOT_MENTION', 'opensuperagent'), os.environ.get('OSA_GITHUB_TOKEN', ''), os.environ.get('OSA_CANDIDATE_LABEL', 'agent-candidate')) if os.environ.get('OSA_GITHUB_POLL') == '1' else None
    server = make_server(store, executor, Path(__file__).parent.parent / 'dist', args.port)
    stop = threading.Event()

    def schedule():
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = []
            while not stop.wait(1):
                active = [f for f in active if not f.done()]
                if len(active) < 2:
                    task_id = store.claim()
                    if task_id:
                        active.append(pool.submit(executor.run, task_id))

    worker = threading.Thread(target=schedule, daemon=True)
    worker.start()
    if source:
        def watch():
            last_error = None
            while not stop.is_set():
                try:
                    source.poll()
                    if last_error:
                        store.log(None, 'source', 'GitHub polling recovered.')
                    last_error = None
                except Exception as e:
                    reason = type(e).__name__
                    if reason != last_error:
                        store.log(None, 'source', 'GitHub polling failed (' + reason + '). Cursor retained; retries every 60 seconds.')
                    last_error = reason
                stop.wait(60)

        threading.Thread(target=watch, daemon=True).start()
    print('OpenSuperAgent: http://127.0.0.1:' + str(server.server_port), flush=True)
    print('Execution: ' + ('configured; 2 workers, 20 model steps per attempt' if executor.repo and provider else 'disabled until OSA_REPO and OSA_API_KEY are set'), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        # Active requests may finish; interrupted attempts recover as blocked on restart.


if __name__ == '__main__':
    main()
