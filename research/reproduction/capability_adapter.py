"""Benchmark transport adapters; frozen source025 and upstream mini agent stay unchanged."""
import asyncio
import json
import time
from types import SimpleNamespace

from osa_eval.contracts import canonical


class MiniModel:
    def __init__(self, transport, journal, config):
        self.transport, self.journal, self.config = transport, journal, config

    def query(self, messages, **kwargs):
        from minisweagent.exceptions import FormatError
        from minisweagent.models.utils.actions_toolcall import parse_toolcall_actions, BASH_TOOL
        clean = [{k: v for k, v in m.items() if k != 'extra'} for m in messages]
        async def request():
            preflight = await self.transport.prepare(clean, [BASH_TOOL])
            call = self.journal.reserve('worker', 'mini', preflight['reservation_tokens'], details=preflight)
            self.journal.trace('model_request', call_id=call, role='worker', session='mini', messages=clean, tools=[BASH_TOOL])
            try:
                reply = await self.transport.complete(clean, [BASH_TOOL], role='worker')
            except BaseException:
                self.journal.uncertain(call)
                raise
            self.journal.finish(call, reply.usage)
            self.journal.trace('model_response', call_id=call, role='worker', session='mini', message=reply.message,
                               response_model=reply.model, finish_reason=reply.finish_reason)
            return reply
        reply = asyncio.run(request())
        extra = {'cost': 0., 'timestamp': time.time(), 'actual_usage': reply.usage.__dict__,
                 'finish_reason': reply.finish_reason, 'cost_convention': 'No commercial API charge; GPU residence separate'}
        try:
            calls = [SimpleNamespace(id=c['id'], function=SimpleNamespace(**c['function']))
                     for c in reply.message.get('tool_calls') or []]
            actions = parse_toolcall_actions(calls, format_error_template=self.config['format_error_template'],
                template_kwargs={'finish_reason': reply.finish_reason})
        except FormatError as error:
            error.messages[0]['extra'].update(extra, model_response=reply.message)
            raise
        return {**reply.message, 'extra': {**extra, 'actions': actions}}

    def format_message(self, **kwargs):
        return kwargs

    def format_observation_messages(self, message, outputs, template_vars=None):
        from minisweagent.models.utils.actions_toolcall import format_toolcall_observation_messages
        return format_toolcall_observation_messages(actions=message['extra']['actions'], outputs=outputs, observation_template=self.config['observation_template'],
                                            template_vars=template_vars)

    def get_template_vars(self, **kwargs):
        return {'model_name': self.transport.model, **kwargs}

    def serialize(self):
        return {'info': {'model_adapter': 'shared exact-token reservation and ChatModel transport',
                         'model_identity': self.transport.identity, 'usage': self.journal.usage()}}


class MiniEnvironment:
    def __init__(self, workspace, journal, timeout_s, deadline):
        self.workspace, self.journal, self.timeout_s, self.deadline = workspace, journal, timeout_s, deadline
        probe = asyncio.run(workspace.execute('uname -srm', 10))
        if probe['returncode']:
            raise RuntimeError('Task system identity unavailable')
        system, release, machine = probe['stdout'].strip().split()
        self.vars = dict(system=system, release=release, machine=machine, version='Linux', cwd=workspace.cwd)

    def execute(self, action, cwd=''):
        from minisweagent.environments.local import LocalEnvironment
        command = action['command']
        if not isinstance(command, str) or len(command) > 100000:
            raise ValueError('Invalid command')
        timeout = min(self.timeout_s, self.deadline - time.monotonic() - 6)
        if timeout <= 0:
            raise TimeoutError('Task deadline reached')
        self.journal.trace('tool_started', command=command, tool_name='bash')
        result = asyncio.run(self.workspace.execute(command, timeout))
        self.journal.trace('tool_finished', command=command, result=result)
        output = {'output': result['stdout'] + result['stderr'], 'returncode': result['returncode'], 'exception_info': ''}
        LocalEnvironment._check_finished(self, output)
        return output

    def get_template_vars(self, **kwargs):
        return self.vars | kwargs

    def serialize(self):
        return {'info': {'environment_adapter': 'same DockerWorkspace as source025', 'workspace': self.workspace.identity}}


def mini_work(transport, journal, workspace, task, limits, config, output):
    from minisweagent.agents.default import DefaultAgent
    env = MiniEnvironment(workspace, journal, limits.tool_timeout_s, time.monotonic() + limits.task_timeout_s)
    agent = DefaultAgent(MiniModel(transport, journal, config['model']), env,
                         **({k:v for k,v in config['agent'].items() if k != 'mode'} | {'step_limit': limits.max_steps, 'cost_limit': 0.,
                            'wall_time_limit_seconds': int(limits.task_timeout_s), 'output_path': output / 'mini.traj.json'}))
    return agent.run(task.instruction)
