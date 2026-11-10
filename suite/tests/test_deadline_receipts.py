import asyncio
from pathlib import Path
import tempfile
import unittest

from osa_eval.contracts import Limits, Reply, Usage
from osa_suite.budget import BudgetLedger, SharedBudgetJournal
from osa_suite.runtime import RoutingChargedKernel


class GatedModel:
    def __init__(self, *, fail=False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.fail = fail

    async def complete(self, messages, tools, *, role):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError('Provider returned no usage')
        return Reply({
            'role': 'assistant',
            'tool_calls': [{'id': 'late', 'function': {'name': 'execute', 'arguments': '{"command":"touch late"}'}}],
        }, Usage(4, 3), 'fixture', 'tool_calls')


class Workspace:
    def __init__(self):
        self.commands = []

    async def execute(self, command, timeout_s):
        self.commands.append(command)
        return {'stdout': '', 'stderr': '', 'returncode': 0}


class DeadlineReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.ledger = BudgetLedger(root / 'campaign.sqlite3', campaign_limit=100, task_limit=100, identity={})
        self.journal = SharedBudgetJournal(root / 'run.sqlite3', token_budget=100, identity={},
                                           ledger=self.ledger, task_key='task')

    def kernel(self, model):
        limits = Limits(model_concurrency=1, token_budget=100, request_token_reservation=10)
        return RoutingChargedKernel(model, self.journal, limits)

    async def test_deadline_keeps_receipt_and_discards_late_tool_call(self):
        model = GatedModel()
        kernel = self.kernel(model)
        workspace = Workspace()
        worker = asyncio.create_task(kernel.work('task', 'fixture', workspace, execution_timeout_s=0.2))
        await asyncio.wait_for(model.started.wait(), 2)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(worker, 2)

        self.assertTrue(kernel.model_slots.locked())
        self.assertEqual(self.ledger.summary()['outstanding_reserved_tokens'], 10)
        self.assertEqual(workspace.commands, [])
        next_call = asyncio.create_task(kernel.ask('other', 'worker', [], []))
        await asyncio.sleep(0)
        self.assertEqual(model.calls, 1)

        model.release.set()
        await asyncio.wait_for(kernel.settle_model_receipts(), 2)
        await asyncio.wait_for(next_call, 2)
        self.assertEqual(workspace.commands, [])
        self.assertEqual(model.calls, 2)
        self.assertTrue(self.ledger.summary()['accounting_valid'])
        self.assertEqual(self.ledger.summary()['actual_api_tokens'], 14)
        self.assertEqual(self.journal.usage()['actual_api_tokens'], 14)

    async def test_cancellation_during_preflight_sends_no_generation(self):
        class PreflightModel(GatedModel):
            async def prepare(self, messages, tools):
                self.started.set()
                await self.release.wait()

        model = PreflightModel()
        kernel = self.kernel(model)
        caller = asyncio.create_task(kernel.ask('worker', 'worker', [], []))
        await asyncio.wait_for(model.started.wait(), 2)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        model.release.set()
        await kernel.settle_model_receipts()
        self.assertEqual(model.calls, 0)
        self.assertEqual(self.ledger.summary()['calls'], [])
        self.assertFalse(kernel.model_slots.locked())

    async def test_missing_receipt_after_cancellation_remains_invalid(self):
        model = GatedModel(fail=True)
        kernel = self.kernel(model)
        caller = asyncio.create_task(kernel.ask('worker', 'worker', [], []))
        await asyncio.wait_for(model.started.wait(), 2)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        model.release.set()
        await asyncio.wait_for(kernel.settle_model_receipts(), 2)
        self.assertFalse(self.ledger.summary()['accounting_valid'])
        self.assertEqual(self.ledger.summary()['outstanding_reserved_tokens'], 10)
        self.assertFalse(self.journal.usage()['accounting_valid'])
