"""Stage 2 controller; frozen source025 Kernel and durable registry are reused.

Only router model HISTORY varies with persistence. Task, input, and subscription
registry state is durable in all C0-C3 cells. Subscription routing does not call a
model. Task-level scope: no claim of recursive intra-task coding decomposition.
"""
from __future__ import annotations

import asyncio
import json
import time

from osa_eval.contracts import canonical, model_event
from osa_eval.runtime import Runtime, ROUTE, ROUTER_PROMPT
from osa_eval.kernel import WORKER_PROMPT, Kernel

from .budget import CURRENT_TASK, REQUEST_ADMITTED


CELLS = {'C0': (False, False), 'C1': (True, False), 'C2': (False, True), 'C3': (True, True)}


class RoutingChargedKernel(Kernel):
    """Retain the Worker loop; charge router time against its task active cap.

    Independent Pro requests only. External task queue time is reported in
    completion latency; router model queue/inference time consumes agent time.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.routing_s = {}
        self._pending_model_receipts = set()

    async def ask(self, session, role, messages, tools):
        started = time.monotonic()
        admitted = asyncio.Event()
        token = REQUEST_ADMITTED.set(admitted)
        try:
            request = asyncio.create_task(super().ask(session, role, messages, tools))
        finally:
            REQUEST_ADMITTED.reset(token)
        try:
            return await asyncio.shield(request)
        except asyncio.CancelledError:
            if admitted.is_set():
                # The Worker stops here. The admitted request still holds its
                # model slot and records usage, without returning a late reply.
                self._pending_model_receipts.add(request)
                self.journal.trace('model_receipt_deferred', role=role, session=session,
                                   task_id=CURRENT_TASK.get())
            else:
                request.cancel()
                await asyncio.gather(request, return_exceptions=True)
            raise
        finally:
            if role == 'router':
                task = CURRENT_TASK.get()
                self.routing_s[task] = self.routing_s.get(task, 0) + time.monotonic() - started

    async def settle_model_receipts(self):
        """Wait for admitted calls whose task stopped before the response."""
        receipts = tuple(self._pending_model_receipts)
        if receipts:
            # Kernel.ask records either the actual receipt or unknown usage.
            # Batch accounting checks both journals before accepting any grade.
            await asyncio.gather(*(asyncio.shield(request) for request in receipts), return_exceptions=True)
            self._pending_model_receipts.difference_update(receipts)

    async def work(self, task_id, instruction, workspace, **kwargs):
        if kwargs.get('execution_timeout_s') is not None:
            remaining = kwargs['execution_timeout_s'] - self.routing_s.get(task_id, 0)
            if remaining <= 0:
                raise TimeoutError('Router exhausted this task agent-time allowance')
            kwargs['execution_timeout_s'] = remaining
        return await super().work(task_id, instruction, workspace, **kwargs)


class TaskBudgetRuntime(Runtime):
    """Attach routing and execution to the same logical task budget."""
    async def _route(self, event):
        if event.kind != 'request' and event.task_id is None:
            targets = self.journal.subscribers(event.thread) if self.subscriptions and self.architecture == 'superagent' else []
            if not targets:
                raise ValueError('Unsubscribed follow-ups need an explicit task for budget attribution')
        token = CURRENT_TASK.set(event.task_id or event.id)
        try:
            return await super()._route(event)
        finally:
            CURRENT_TASK.reset(token)

    async def _execute(self, row, workspace):
        token = CURRENT_TASK.set(row['id'])
        try:
            return await super()._execute(row, workspace)
        finally:
            CURRENT_TASK.reset(token)


class ArchitectureRuntime(TaskBudgetRuntime):
    """Five task-level conditions with fresh main routing in Subagent/Eager.

    Every benchmark task starts a separate Worker history in every architecture.
    The serial baseline and dynamic main may use only one main execution at once;
    delegated workers share the same four-slot ceiling. Router roles use the same
    common model endpoint, decoding, and aggregate budget as Workers.
    """
    async def _decision(self, event):
        if self.architecture not in {'single_subagent', 'eager_delegation'}:
            return await super()._decision(event)
        session = 'main-router:' + event.id
        messages, state = self.journal.session(session)
        if state in {'model_pending', 'tool_pending'}:
            raise RuntimeError('Main routing has an uncertain interrupted turn')
        if not messages:
            messages = [{'role': 'system', 'content': WORKER_PROMPT}]
        force = self.architecture == 'eager_delegation'
        messages.append({'role': 'user', 'content': ROUTER_PROMPT +
                        ('\nThis condition requires delegation.' if force else '\nChoose freely; delegation is optional.') +
                        '\nEvent: ' + canonical(model_event(event))})
        self.journal.save(session, messages, 'model_pending')
        response = await self.kernel.ask(session, 'router', messages, [ROUTE])
        calls = response.get('tool_calls') or []
        if len(calls) != 1 or calls[0]['function']['name'] != 'route':
            raise ValueError('Main must emit one route call')
        args = json.loads(calls[0]['function']['arguments'])
        if set(args) != {'action'} or args['action'] not in {'self', 'delegate'} or force and args['action'] != 'delegate':
            raise ValueError('Invalid main delegation decision')
        messages += [response, {'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': canonical({'accepted': args['action']})}]
        self.journal.save(session, messages)
        return args['action']

    async def _route(self, event):
        if self.architecture not in {'single', 'single_subagent'}:
            return await super()._route(event)
        task = event.task_id or event.id
        token = CURRENT_TASK.set(task)
        try:
            action = await self._decision(event)
            self.journal.assign(event, task, ('main:' if action == 'self' else 'worker:') + task,
                                'main' if action == 'self' else 'worker', subscribe=False)
        finally:
            CURRENT_TASK.reset(token)

    async def _execute(self, row, workspace):
        if row['role'] == 'main':
            async with self.single_lock:
                return await super()._execute(row, workspace)
        return await super()._execute(row, workspace)

    async def _notify(self, row):
        if self.architecture == 'superagent':
            await super()._notify(row)
        else:
            self.journal.trace('worker_status_in_registry', task_id=row['id'])


class MechanismRuntime(TaskBudgetRuntime):
    def __init__(self, cell, kernel, *, on_task_update=None):
        if cell not in CELLS:
            raise ValueError('Expected C0, C1, C2, or C3')
        self.cell = cell
        self.persistent, subscribed = CELLS[cell]
        # Parent only supplies worker lifecycle, queueing, and recovery; routing
        # and completion history below are shared across all four cells.
        super().__init__('superagent', kernel, subscriptions=subscribed, on_task_update=on_task_update)

    async def _decision(self, event):
        session = 'router' if self.persistent else 'router:' + event.id
        lock = self.kernel.session_locks.setdefault(session, asyncio.Lock())
        async with lock:
            messages, state = self.journal.session(session)
            if state in {'model_pending', 'tool_pending'}:
                raise RuntimeError('Router has an uncertain interrupted turn')
            if not messages:
                messages = [{'role': 'system', 'content': ROUTER_PROMPT}]
            messages.append({'role': 'user', 'content': ROUTER_PROMPT +
                             '\nThis condition requires delegation.\nEvent: ' + canonical(model_event(event))})
            self.journal.save(session, messages, 'model_pending')
            message = await self.kernel.ask(session, 'router', messages, [ROUTE])
            calls = message.get('tool_calls') or []
            if len(calls) != 1 or calls[0]['function']['name'] != 'route':
                raise ValueError('Router must emit exactly one route call')
            if json.loads(calls[0]['function']['arguments']) != {'action': 'delegate'}:
                raise ValueError('This cell requires delegation')
            messages += [message, {'role': 'tool', 'tool_call_id': calls[0]['id'],
                                  'content': canonical({'accepted': 'delegate'})}]
            self.journal.save(session, messages)
        return 'delegate'

    async def _notify(self, row):
        # Same durable status is visible in the registry for all cells. Only the
        # persistent model-history condition additionally retains status messages.
        if self.persistent:
            await super()._notify(row)

    async def run(self, events, workspaces):
        self.journal.trace('mechanism_condition', cell=self.cell,
                           persistent_router=self.persistent, subscriptions=self.subscriptions,
                           durable_registry=True, official_benchmark=False)
        return await super().run(events, workspaces)
