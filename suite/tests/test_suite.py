import asyncio
import concurrent.futures
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from osa_eval.contracts import Event, Limits, Reply, Usage
from osa_eval.journal import BudgetExhausted
from osa_eval.kernel import Kernel
from osa_suite.analysis import paired, pareto, summarize
from osa_suite.budget import BudgetLedger, SharedBudgetJournal, CURRENT_TASK
from osa_suite.manifest import schedule, freeze, verify_lock
from osa_suite.report import validate
from osa_suite.runtime import ArchitectureRuntime, MechanismRuntime, RoutingChargedKernel
from osa_suite.selection import select
from osa_suite.native_workspace import role_path


class ScriptedModel:
    identity = {'scripted': True}

    def __init__(self):
        self.calls, self.active, self.maximum = [], 0, 0

    async def complete(self, messages, tools, *, role):
        self.calls.append((role, json.loads(json.dumps(messages))))
        if role == 'router':
            return Reply(dict(role='assistant', content=None, tool_calls=[dict(id='route', type='function',
                 function=dict(name='route', arguments='{"action":"delegate"}'))]), Usage(4, 3), 'scripted')
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(.01)
        self.active -= 1
        return Reply(dict(role='assistant', content='fixture completion, not a grade'), Usage(4, 3), 'scripted')


class Workspace:
    identity = {'scripted': True}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self, cap=100, task=60):
        return BudgetLedger(self.root / 'budget.sqlite3', campaign_limit=cap, task_limit=task, identity={'run': 1})

    def test_atomic_admission_across_independent_connections(self):
        ledger = self.ledger(cap=100, task=100)
        def reserve(_):
            fresh = self.ledger(cap=100, task=100)
            try:
                return fresh.reserve('task', 'worker', 's', 20)
            except BudgetExhausted:
                return None
        with concurrent.futures.ThreadPoolExecutor(12) as pool:
            keys = list(pool.map(reserve, range(12)))
        self.assertEqual(sum(k is not None for k in keys), 5)
        self.assertEqual(ledger.summary()['total_upper_bound'], 100)

    def test_router_worker_retry_share_logical_task(self):
        ledger = self.ledger()
        first = ledger.reserve('task', 'router', 'r', 30)
        ledger.finish(first, Usage(12, 8))
        second = self.ledger().reserve('task', 'worker', 'w', 30)
        ledger.finish(second, Usage(20, 10))
        with self.assertRaises(BudgetExhausted):
            self.ledger().reserve('task', 'retry', 'w', 11)
        other = ledger.reserve('another', 'worker', 'w2', 40)
        ledger.finish(other, Usage(20, 20))
        self.assertEqual(ledger.summary()['actual_api_tokens'], 90)

    def test_unknown_receipt_stops_all_roles_and_survives_restart(self):
        ledger = self.ledger()
        key = ledger.reserve('task', 'worker', 'w', 40)
        ledger.uncertain(key)
        fresh = self.ledger()
        with self.assertRaises(RuntimeError):
            fresh.reserve('another', 'router', 'r', 10)
        self.assertFalse(fresh.summary()['accounting_valid'])
        self.assertIsNone(fresh.summary()['actual_api_tokens'])
        self.assertEqual(fresh.summary()['outstanding_reserved_tokens'], 40)

    def test_overrun_is_durable_and_duplicate_receipt_rejected(self):
        ledger = self.ledger()
        key = ledger.reserve('task', 'worker', 's', 10)
        with self.assertRaises(ValueError):
            ledger.finish(key, Usage(10, 2))
        self.assertEqual(ledger.summary()['observed_api_tokens'], 12)
        self.assertFalse(ledger.summary()['accounting_valid'])
        with self.assertRaises(ValueError):
            ledger.finish(key, Usage(1, 1))

    def test_shared_journal_trace_envelope_and_local_denial_rollback(self):
        ledger = self.ledger()
        journal = SharedBudgetJournal(self.root / 'run.sqlite3', token_budget=10, identity={}, ledger=ledger, task_key='task')
        with self.assertRaises(BudgetExhausted):
            journal.reserve('worker', 's', 11)
        self.assertEqual(ledger.summary()['total_upper_bound'], 0)
        journal.intake(Event('a', 'thread', 'public task'))
        journal.export(self.root / 'export')
        event = json.loads((self.root / 'export/events.v2.jsonl').read_text().splitlines()[-1])
        self.assertEqual(event['event_type'], 'event_received')
        self.assertEqual(event['payload']['kind'], 'request')


class RuntimeTests(unittest.TestCase):
    def exercise(self, condition, mechanism=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = BudgetLedger(root / 'global.sqlite3', campaign_limit=10000, task_limit=5000, identity={})
            journal = SharedBudgetJournal(root / 'run.sqlite3', token_budget=10000, identity={}, ledger=ledger,
                                          task_key=lambda: CURRENT_TASK.get())
            model = ScriptedModel()
            kernel = Kernel(model, journal, Limits(token_budget=10000, request_token_reservation=20, max_steps=3))
            runtime = MechanismRuntime(condition, kernel) if mechanism else ArchitectureRuntime(condition, kernel)
            events = [Event('a', 'thread-a', 'Task A', task_id='a'), Event('b', 'thread-b', 'Task B', task_id='b')]
            if mechanism:
                events += [Event('a1', 'thread-a', 'Follow-up 1', .015, 'a', 'followup'),
                           Event('a2', 'thread-a', 'Follow-up 2', .03, 'a', 'followup')]
            results = asyncio.run(runtime.run(events, {'a': Workspace(), 'b': Workspace()}))
            return model, ledger.summary(), journal.subscribers('thread-a'), results

    def test_five_architectures_same_worker_and_serial_capacity(self):
        for arm in ('single', 'single_subagent', 'eager_delegation', 'router_worker', 'superagent'):
            with self.subTest(arm=arm):
                model, usage, _, results = self.exercise(arm)
                self.assertTrue(usage['accounting_valid'])
                self.assertEqual({r['task'] for r in usage['calls']}, {'a', 'b'})
                self.assertTrue(all(r['state'] == 'completed' for r in results))
                workers = [messages for role, messages in model.calls if role != 'router']
                self.assertEqual(len(workers), 2)
                self.assertEqual(len(workers[0]), 2)  # No other task or route response contaminates Worker.
                if arm == 'single':
                    self.assertEqual(model.maximum, 1)

    def test_full_factorial_subscription_independent_of_router_history(self):
        outputs = {cell: self.exercise(cell, True) for cell in ('C0', 'C1', 'C2', 'C3')}
        for cell, (model, usage, subscribers, _) in outputs.items():
            routers = [messages for role, messages in model.calls if role == 'router']
            self.assertEqual(len(routers), 2 if cell in {'C2', 'C3'} else 4)
            self.assertTrue(usage['accounting_valid'])
            self.assertEqual(subscribers, ['a'] if cell in {'C2', 'C3'} else [])
            if cell in {'C0', 'C2'}:
                self.assertTrue(all(len(messages) == 2 for messages in routers))
            else:
                self.assertGreater(len(routers[-1]), 2)

    def test_router_time_reduces_task_active_allowance(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = BudgetLedger(Path(directory) / 'b.sqlite3', campaign_limit=100, task_limit=100, identity={})
            journal = SharedBudgetJournal(Path(directory) / 'r.sqlite3', token_budget=100, identity={}, ledger=ledger, task_key='a')
            kernel = RoutingChargedKernel(ScriptedModel(), journal, Limits())
            kernel.routing_s['a'] = 30
            async def check():
                with patch.object(Kernel, 'work', return_value='fixture') as original:
                    await kernel.work('a', 'instruction', Workspace(), execution_timeout_s=100)
                    self.assertAlmostEqual(original.call_args.kwargs['execution_timeout_s'], 70)
                kernel.routing_s['a'] = 101
                with self.assertRaises(TimeoutError):
                    await kernel.work('a', 'instruction', Workspace(), execution_timeout_s=100)
            asyncio.run(check())


def result(task, repo, agent, seed, success):
    return dict(track='controlled', benchmark='fixture', protocol='same', task_id=task,
                repository=repo, agent=agent, seed=seed, success=success,
                protocol_valid=True, accounting_valid=True, scoring_valid=True,
                actual_api_tokens=100, completion_s=1)


class ProtocolTests(unittest.TestCase):
    def test_native_role_path_prevents_mount_argument_injection(self):
        self.assertEqual(role_path('/workspace/task_role_1'), '/workspace/task_role_1')
        for value in ('/workspace', '/workspace/../peer', '/workspace/x,readonly', '/other/task'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                role_path(value)

    def test_throughput_uses_complete_batch_wall_once(self):
        rows = [result('t1', 'repo', 'arm', 1, True), result('t2', 'repo', 'arm', 1, True)]
        for row in rows:
            row.update(batch_id='b1', batch_wall_s=10, batch_task_count=2)
        summary = next(iter(summarize(rows).values()))
        self.assertEqual(summary['complete_batch_wall_s'], 10)
        self.assertEqual(summary['successful_tasks_per_batch_hour'], 720)
        self.assertIsNone(next(iter(summarize(rows[:1]).values()))['successful_tasks_per_batch_hour'])

    def test_pairing_keeps_seeds_in_task_clusters(self):
        rows = [result(t, repo, agent, seed, agent == 'A') for t, repo in [('t1', 'r1'), ('t2', 'r2')]
                for agent in ['A', 'B'] for seed in [1, 2, 3]]
        report = paired(rows, 'A', 'B', iterations=200)
        self.assertEqual(report['paired_task_seeds'], 6)
        self.assertEqual(report['task_cluster_ci']['clusters'], 2)
        self.assertEqual(report['repository_cluster_ci']['clusters'], 2)
        self.assertEqual(report['task_mean_success_difference'], 1)
        self.assertEqual(report['task_cluster_ci']['low'], 1)
        rows[-1]['protocol'] = 'different'
        with self.assertRaises(ValueError):
            paired(rows, 'A', 'B')

    def test_report_rejects_duplicate_valid_run_and_unknown_zero_usage(self):
        row = result('t', 'r', 'a', 1, True)
        with self.assertRaises(ValueError):
            validate([row, row])
        row['actual_api_tokens'] = None
        with self.assertRaises(ValueError):
            validate([row])

    def test_stratified_sampling_excludes_development_and_ignores_outcomes(self):
        rows = [dict(task_id=str(i), repository='r' + str(i % 2), language='python',
                    complexity_proxy='short', parallelizability_proxy='unspecified_text', success=i % 3 == 0) for i in range(20)]
        a, _ = select(rows, excluded=['0', '1'], count=6, seed=123)
        b, _ = select([dict(r, success=not r['success']) for r in rows], excluded=['0', '1'], count=6, seed=123)
        self.assertEqual([r['task_id'] for r in a], [r['task_id'] for r in b])
        self.assertFalse({'0', '1'} & {r['task_id'] for r in a})
        self.assertEqual(len(a), 6)

    def test_freeze_detects_modified_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.py').write_text('original')
            freeze(root, root / 'LOCK.json')
            verify_lock(root, root / 'LOCK.json')
            (root / 'source.py').write_text('changed')
            with self.assertRaises(ValueError):
                verify_lock(root, root / 'LOCK.json')
            (root / 'source.py').write_text('original')
            (root / 'extra.py').write_text('unexpected source')
            with self.assertRaises(ValueError):
                verify_lock(root, root / 'LOCK.json')

    def test_arm_order_is_frozen_before_selecting_one_arm(self):
        jobs = schedule(['a', 'b'], ['single', 'eager', 'super'], [1, 2], order_seed=7)
        self.assertEqual(jobs, schedule(['a', 'b'], ['single', 'eager', 'super'], [1, 2], order_seed=7))
        self.assertEqual(len(jobs), 6)
        self.assertTrue(all(j['tasks'] == ['a', 'b'] for j in jobs))

    def test_pareto_retains_tradeoff(self):
        points = [dict(agent='a', success_rate=.5, tokens=10, latency_s=2),
                  dict(agent='b', success_rate=.4, tokens=11, latency_s=3),
                  dict(agent='c', success_rate=.6, tokens=12, latency_s=3)]
        self.assertEqual({r['agent'] for r in pareto(points)}, {'a', 'c'})


if __name__ == '__main__':
    unittest.main()
