"""Read-only GitHub polling. Explicit mentions execute; labeled work is observed."""
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from .core import now


class GitHubSource:
    def __init__(self, store, repository, actors, bot='opensuperagent', token='', label='agent-candidate'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('OSA_GITHUB_REPO must be owner/repository.')
        self.store, self.repository, self.actors, self.bot, self.token, self.label = store, repository, set(actors), bot, token, label
        self.cursor_key = 'github_cursor:' + repository

    def poll(self, fetch=None):
        with self.store.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (self.cursor_key,)).fetchone()
            since = row[0] if row else now()
            if not row:
                db.execute('INSERT INTO settings VALUES(?,?)', (self.cursor_key, since))
        # Overlap one second; durable trigger identities make repeated pages harmless.
        cutoff = (datetime.fromisoformat(since) - timedelta(seconds=1)).astimezone(timezone.utc).isoformat()
        from urllib.parse import urlencode
        url = 'https://api.github.com/repos/' + self.repository + '/issues?' + urlencode({'state': 'open', 'sort': 'updated', 'direction': 'asc', 'since': cutoff, 'per_page': 100})
        high = since
        for page in range(1, 11):
            if fetch:
                issues = fetch(url + '&page=' + str(page))
            else:
                headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'OpenSuperAgent/0.1'}
                if self.token:
                    headers['Authorization'] = 'Bearer ' + self.token
                req = urllib.request.Request(url + '&page=' + str(page), headers=headers)
                with urllib.request.urlopen(req, timeout=20) as response:
                    issues = json.load(response)
            if not isinstance(issues, list):
                raise ValueError('GitHub returned an invalid issue list.')
            for issue in issues:
                updated = issue.get('updated_at', '')
                if updated and datetime.fromisoformat(updated.replace('Z', '+00:00')) > datetime.fromisoformat(high.replace('Z', '+00:00')):
                    high = updated
                if issue.get('pull_request') or issue.get('user', {}).get('type') == 'Bot':
                    continue
                actor = issue.get('user', {}).get('login', '')
                if actor not in self.actors:
                    continue
                body = issue.get('body') or ''
                mentioned = re.search(r'(?<![\w-])@' + re.escape(self.bot) + r'(?![\w-])', body, re.I)
                labels = {x.get('name') for x in issue.get('labels', []) if isinstance(x, dict)}
                if not mentioned and self.label not in labels:
                    continue
                # One issue yields one task, even if edited or also delivered by webhook.
                self.store.create(str(issue.get('title', 'GitHub request'))[:160], body or str(issue.get('title', 'Review this issue')), source='github' if mentioned else 'rule', actor=actor,
                                  trigger_id='github-issue:' + self.repository + ':' + str(issue['number']), inferred=not bool(mentioned))
            if len(issues) < 100:
                break
        else:
            # Leave cursor unchanged rather than silently skipping beyond the page budget.
            raise ValueError('GitHub source exceeded 1,000 updates per poll. Narrow the source or use webhooks.')
        with self.store.connect() as db:
            db.execute('UPDATE settings SET value=? WHERE key=?', (high, self.cursor_key))
