import asyncio
import json
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from osa_eval.contracts import Event, Limits, Reply, Usage, digest
from osa_eval.journal import BudgetExhausted, Journal
from osa_eval.kernel import Kernel
from osa_eval.metrics import paired_bootstrap, summarize, validate_comparison, COMMON_FIELDS
from osa_eval.model import ChatModel
from osa_eval.runtime import Runtime
from osa_eval.smoke import DiagnosticModel, DiagnosticWorkspace, run_smoke
from osa_eval.workload import schedule, select_tasks
from osa_eval.campaign import balanced_arm_order, ProCampaign
from osa_eval.swebench_pro import compilation_diagnostics


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'run.db'
        self.j = Journal(self.path, token_budget=100, identity={'model':'fixed'})

    def tearDown(self):
        self.temp.cleanup()

    def test_concurrent_reservations_never_overadmit(self):
        def admit(_):
            try:
                return self.j.reserve('worker','s',30)
            except BudgetExhausted:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(filter(None,pool.map(admit,range(12))))
        self.assertEqual(len(accepted),3)
        for call in accepted:
            self.j.finish(call,Usage(10,5))
        self.assertTrue(self.j.usage()['accounting_valid'])
        self.assertEqual(self.j.usage()['input_tokens'],30)
        self.assertEqual(self.j.usage()['output_tokens'],15)
        self.assertIsNone(self.j.usage()['cost_usd'])

    def test_unknown_billed_call_keeps_reservation_and_invalidates(self):
        call = self.j.reserve('router','s',80)
        self.j.uncertain(call)
        self.assertFalse(self.j.usage()['accounting_valid'])
        self.assertIsNone(self.j.usage()['actual_api_tokens'])
        self.assertEqual(self.j.usage()['observed_api_tokens'], 0)
        with self.assertRaises(BudgetExhausted):
            self.j.reserve('worker','s2',30)

    def test_denied_reservation_is_durable_and_is_not_an_api_call(self):
        first = self.j.reserve('worker', 's', 80)
        self.j.finish(first, Usage(60, 10))
        with self.assertRaises(BudgetExhausted):
            self.j.reserve('router', 'r', 40, details={'prompt_tokens': 30, 'max_output_tokens': 10})
        reopened = Journal(self.path, token_budget=100, identity={'model': 'fixed'}).usage()
        self.assertEqual(len(reopened['calls']), 1)
        self.assertEqual(reopened['actual_api_tokens'], 70)
        self.assertEqual(reopened['accepted_reservation_tokens_sum'], 80)
        self.assertEqual(reopened['outstanding_reserved_tokens'], 0)
        self.assertEqual(reopened['reservation_denied_count'], 1)
        self.assertEqual(reopened['reservation_denials'][0]['requested_tokens'], 40)

    def test_usage_overrun_is_charged_and_invalid(self):
        call=self.j.reserve('worker','s',30)
        with self.assertRaises(ValueError):
            self.j.finish(call,Usage(30,10))
        self.assertEqual(self.j.usage()['input_tokens'],30)
        self.assertFalse(self.j.usage()['accounting_valid'])

    def test_resume_freezes_model_and_budget(self):
        with self.assertRaises(ValueError):
            Journal(self.path,token_budget=100,identity={'model':'changed'})
        with self.assertRaises(ValueError):
            Journal(self.path,token_budget=101,identity={'model':'fixed'})

    def test_event_idempotence_and_payload_collision(self):
        e=Event('e','thread','task')
        self.assertTrue(self.j.intake(e))
        again=Journal(self.path,token_budget=100,identity={'model':'fixed'})
        self.assertFalse(again.intake(e))
        with self.assertRaises(ValueError):
            again.intake(Event('e','thread','different'))

    def test_many_to_many_and_input_checkpoint(self):
        for task in ['a','b']:
            self.j.subscribe('thread',task)
        self.assertEqual(self.j.subscribers('thread'),['a','b'])
        e=Event('e','thread','update',kind='followup')
        self.j.deliver(e,'a');self.j.deliver(e,'a')
        messages=self.j.take_inputs('a','sa',[])
        self.assertEqual(len(messages),1)
        self.assertEqual(self.j.take_inputs('a','sa',messages),messages)
        self.assertEqual(self.j.session('sa')[0],messages)


class WorkloadTests(unittest.TestCase):
    def test_arm_order_balances_each_position_without_outcome_selection(self):
        order=balanced_arm_order(10,seed=7)
        self.assertEqual(order,balanced_arm_order(10,seed=7))
        for position in range(5):
            self.assertEqual(len({row[position] for row in order[:5]}),5)
    def test_self_hosted_http_is_explicit_and_limited_to_private_ip(self):
        with self.assertRaises(ValueError):ChatModel('http://192.168.16.18:8000/v1','test','model')
        ChatModel('http://192.168.16.18:8000/v1','test','model',allow_private_http=True)
        with self.assertRaises(ValueError):ChatModel('http://1.1.1.1/v1','test','model',allow_private_http=True)

    def test_sampling_is_independent_of_input_order(self):
        self.assertEqual(select_tasks(['c','a','b'],2,4),select_tasks(['b','a','c'],2,4))
        with self.assertRaises(ValueError):select_tasks(['a','a'],1,4)

    def test_seeded_open_loop_arrivals(self):
        tasks=[{'id':str(i),'instruction':'task'} for i in range(9)]
        a=schedule(tasks,seed=7,burst_size=4,interval_s=10)
        self.assertEqual(a,schedule(tasks,seed=7,burst_size=4,interval_s=10))
        self.assertEqual([e['arrival_s'] for e in a['events']],[0]*4+[10]*4+[20])
        p=schedule(tasks,seed=7,mode='poisson',rate_per_s=.2)
        self.assertEqual(p,schedule(tasks,seed=7,mode='poisson',rate_per_s=.2))
        with self.assertRaises(ValueError):schedule(tasks,mode='poisson')


class MetricTests(unittest.TestCase):
    def test_real_unused_import_failure_is_coding_failure_and_permission_failure_is_separate(self):
        log='lib/srv/db/ca.go:21:2: imported and not used: "fmt"\n'
        self.assertEqual(compilation_diagnostics(log),[log.strip()])
        self.assertEqual(compilation_diagnostics('go: mkdir /root/cache: permission denied'),[])
        self.assertEqual(compilation_diagnostics(log+'permission denied'),[])
        self.assertEqual(compilation_diagnostics(log+'\n/usr/local/go/pkg/tool/linux_amd64/compile: signal: segmentation fault'),[])
    def test_unfinished_tasks_remain_in_denominator(self):
        rows=[{'task_id':'a','seed':0,'arrival_s':0,'submitted_s':10,'success':True,'grade_source_sha256':'abc','valid':True},
              {'task_id':'b','seed':0,'arrival_s':0,'submitted_s':None,'success':None,'valid':True}]
        r=summarize(rows,horizon_s=100)
        self.assertEqual(r['success_rate'],.5)
        self.assertEqual(r['right_censored_count'],1)
        self.assertEqual(r['mean_capped_time_in_system_s_all_valid'],55)

    def test_self_reported_success_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize([{'task_id':'a','seed':0,'arrival_s':0,'submitted_s':10,'success':True,'valid':True}],horizon_s=100)

    def test_bootstrap_pairs_seeds_and_clusters_by_task(self):
        r=paired_bootstrap({'a':{0:0,1:0},'b':{0:0,1:0}},{'a':{0:1,1:1},'b':{0:1,1:1}},samples=100)
        self.assertEqual(r['ci95'],[1,1]);self.assertEqual(r['task_clusters'],2)
        with self.assertRaises(ValueError):paired_bootstrap({'a':{0:0}},{'a':{1:1}},samples=10)

    def test_comparison_rejects_missing_or_changed_controls(self):
        c={k:'same' for k in COMMON_FIELDS}
        c.update(slots=4,model_concurrency=4,model_rate_limit=100,horizon_s=100)
        self.assertEqual(validate_comparison([c,dict(c)],'capacity')['configuration_count'],2)
        with self.assertRaises(ValueError):validate_comparison([c,{**c,'slots':8}],'capacity')
        with self.assertRaises(ValueError):validate_comparison([c,c],'budget')

    def test_token_matched_comparison_does_not_require_invented_dollar_cost(self):
        c={k:'same' for k in COMMON_FIELDS}
        c.update(budget_unit='tokens',token_budget=100_000)
        self.assertEqual(validate_comparison([c,c],'budget')['mode'],'budget')
        with self.assertRaises(ValueError):validate_comparison([c,{**c,'budget_unit':'usd','cost_budget_usd':1}],'budget')


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()

    async def asyncTearDown(self):self.temp.cleanup()

    def kernel(self,model=None,**kw):
        limits=Limits(request_token_reservation=1000,token_budget=100_000,**kw)
        j=Journal(Path(self.temp.name)/'run.db',token_budget=limits.token_budget,identity={'purpose':'test'})
        return Kernel(model or DiagnosticModel(),j,limits)

    async def test_known_cutoff_is_charged_without_tool_execution_and_next_task_can_run(self):
        class CutoffThenComplete(DiagnosticModel):
            calls = 0
            async def complete(self, messages, tools, *, role):
                self.calls += 1
                if self.calls == 1:
                    return Reply({'role': 'assistant', 'tool_calls': [{'id': 'cut', 'type': 'function',
                        'function': {'name': 'execute', 'arguments': json.dumps({'command': 'cat >x <<EOF\npartial'})}}]},
                        Usage(10, 8), 'fixed', 'length')
                return Reply({'role': 'assistant', 'content': 'second completed'}, Usage(10, 2), 'fixed')
        model = CutoffThenComplete(); kernel = self.kernel(model)
        with self.assertRaisesRegex(RuntimeError, 'stopped with length'):
            await kernel.work('first', 'first task', DiagnosticWorkspace(), session='main')
        self.assertEqual(kernel.journal.session('main')[1], 'idle')
        self.assertEqual(await kernel.work('second', 'second task', DiagnosticWorkspace(), session='main'), 'second completed')
        self.assertEqual(model.calls, 2)
        usage = kernel.journal.usage()
        self.assertTrue(usage['accounting_valid']); self.assertEqual(usage['actual_api_tokens'], 30)
        self.assertEqual(usage['outstanding_reserved_tokens'], 0)

    async def test_denied_call_leaves_reusable_session_and_no_billed_request(self):
        kernel = self.kernel()
        kernel.journal.save('main', [], 'model_pending')
        kernel.limits = Limits(request_token_reservation=200000, token_budget=100000)
        with self.assertRaises(BudgetExhausted):
            await kernel.ask('main', 'main', [], [])
        self.assertEqual(kernel.journal.session('main')[1], 'idle')
        self.assertEqual(kernel.journal.usage()['calls'], [])
        kernel.limits = Limits(request_token_reservation=1000, token_budget=100000)
        self.assertIn('Diagnostic completion', await kernel.work('second', 'second task', DiagnosticWorkspace(), session='main'))

    async def test_unknown_model_failure_keeps_pending_session_and_blocks_replay(self):
        class Unknown(DiagnosticModel):
            async def complete(self, *args, **kwargs): raise OSError('connection lost before receipt')
        kernel = self.kernel(Unknown())
        with self.assertRaises(OSError):
            await kernel.work('first', 'first task', DiagnosticWorkspace(), session='main')
        self.assertEqual(kernel.journal.session('main')[1], 'model_pending')
        with self.assertRaisesRegex(RuntimeError, 'uncertain outcome'):
            await kernel.work('second', 'second task', DiagnosticWorkspace(), session='main')
        self.assertFalse(kernel.journal.usage()['accounting_valid'])

    async def test_exact_reservation_uses_request_bound_and_requires_preflight(self):
        class Counted(DiagnosticModel):
            async def prepare(self, messages, tools):
                return {'prompt_tokens': 60, 'max_output_tokens': 20, 'max_model_len': 1000}
            async def complete(self, messages, tools, *, role):
                return Reply({'role': 'assistant', 'content': 'done'}, Usage(60, 10), 'fixed')
        limits = Limits(token_budget=100, request_token_reservation=1000,
                        reservation_policy='exact_prompt_plus_max_output')
        journal = Journal(Path(self.temp.name)/'exact.db', token_budget=100, identity={'purpose':'exact'})
        kernel = Kernel(Counted(), journal, limits)
        self.assertEqual(await kernel.work('a', 'task', DiagnosticWorkspace()), 'done')
        self.assertEqual(journal.usage()['calls'][0]['reserved'], 80)
        with self.assertRaises(BudgetExhausted):
            await kernel.ask('other', 'router', [], [])
        self.assertEqual(journal.usage()['reservation_denied_count'], 1)
        missing = Kernel(DiagnosticModel(), journal, limits)
        with self.assertRaisesRegex(ValueError, 'serving tokenizer'):
            await missing.ask('missing', 'worker', [], [])
        self.assertEqual(len(journal.usage()['calls']), 1)

    async def test_session_queue_wait_is_separate_from_task_execution_budget(self):
        class Slow(DiagnosticModel):
            async def complete(self, *args, **kwargs):
                await asyncio.sleep(.24)
                return await super().complete(*args, **kwargs)
        kernel = self.kernel(Slow(), slots=2, model_concurrency=2, task_timeout_s=.4)
        result = await Runtime('single', kernel).run([Event('a','a','first'), Event('b','b','second')],
                                                   {'a':DiagnosticWorkspace(), 'b':DiagnosticWorkspace()})
        self.assertTrue(all(row['state']=='completed' for row in result))

    async def test_tool_cleanup_grace_stays_inside_execution_deadline(self):
        class UsesTool(DiagnosticModel):
            async def complete(self, messages, tools, *, role):
                return Reply({'role':'assistant','content':None,'tool_calls':[{'id':'tool',
                    'type':'function','function':{'name':'execute','arguments':'{"command":"true"}'}}]},
                    Usage(10, 5), 'fixed')
        class Shell(DiagnosticWorkspace):
            cleanup_grace_s = 6
            async def execute(self, command, timeout_s):
                raise AssertionError('An insufficiently bounded command must not start')
        with self.assertRaisesRegex(TimeoutError, 'safely bounded'):
            await self.kernel(UsesTool()).work('a', 'task', Shell(), execution_timeout_s=.5)

    async def test_all_five_architectures_smoke(self):
        r=await run_smoke(Path(self.temp.name)/'smoke')
        self.assertEqual(len(r),5);self.assertTrue(all(x['passed'] for x in r))
        self.assertEqual(r[-1]['model_calls'],5)  # one followup bypasses router

    async def test_campaign_identity_with_chinese_and_emoji_is_portable_utf8(self):
        class Task:
            instruction = '修复加法，并保留说明 📘'
            files = {'instruction.md': 'fixed-input'}
        def unavailable(*args):
            raise RuntimeError('Diagnostic workspace unavailable')
        output = Path(self.temp.name) / '中文运行'
        gate = {'task_files': Task.files, 'image_id': 'fixed-image',
                'empty': {'valid': True, 'success': False},
                'reference': {'valid': True, 'success': True}}
        campaign = ProCampaign({'task': Task()}, DiagnosticModel(), self.kernel().limits,
            unavailable, source_identity={'label': '中文源码 📘'}, evaluator_gates={'task': gate})
        with self.assertRaisesRegex(RuntimeError, 'Diagnostic workspace unavailable'):
            await campaign.run('single', [Event('request', 'thread', Task.instruction, task_id='task')],
                               output, seed=1, horizon_s=10)
        identity = json.loads((output / 'identity.json').read_bytes().decode('utf-8'))
        self.assertEqual(identity['events'][0]['text'], Task.instruction)
        self.assertEqual(identity['source']['label'], '中文源码 📘')

    async def test_shared_single_session_and_optional_direct_execution(self):
        class Direct(DiagnosticModel):
            async def complete(self,messages,tools,*,role):
                reply=await super().complete(messages,tools,role=role)
                if tools[0]['function']['name']=='route':
                    reply.message['tool_calls'][0]['function']['arguments']='{"action":"self"}'
                return reply
        k=self.kernel(Direct())
        result=await Runtime('single_subagent',k).run([Event('a','a','task A'),Event('b','b','task B')],{'a':DiagnosticWorkspace(),'b':DiagnosticWorkspace()})
        self.assertTrue(all(t['session']=='main' for t in result))
        self.assertEqual(len([m for m in k.journal.session('main')[0] if str(m.get('content','')).startswith('Continue assigned task')]),2)

    async def test_arrivals_continue_during_slow_router(self):
        class Slow(DiagnosticModel):
            async def complete(self,*args,**kw):
                if args[1][0]['function']['name']=='route':
                    while not any(e.id=='b' for e in k.journal.pending()):
                        await asyncio.sleep(.001)
                return await super().complete(*args,**kw)
        k=self.kernel(Slow())
        await asyncio.wait_for(Runtime('router_worker',k).run([Event('a','a','A'),Event('b','b','B',arrival_s=.005)],{'a':DiagnosticWorkspace(),'b':DiagnosticWorkspace()}),3)
        with k.journal.db() as db:
            traces=[dict(r) for r in db.execute("SELECT seq,kind,payload FROM trace ORDER BY seq")]
        second=next(r['seq'] for r in traces if r['kind']=='arrival' and json.loads(r['payload'])['event_id']=='b')
        response=next(r['seq'] for r in traces if r['kind']=='model_response')
        self.assertLess(second,response)

    async def test_cancelled_workload_cancels_workers_and_future_arrivals(self):
        class Slow(DiagnosticModel):
            async def complete(self,messages,tools,*,role):
                if role=='worker':await asyncio.Event().wait()
                return await super().complete(messages,tools,role=role)
        k=self.kernel(Slow());runtime=Runtime('superagent',k)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(runtime.run([Event('a','a','A'),Event('b','b','B',arrival_s=100)],{'a':DiagnosticWorkspace(),'b':DiagnosticWorkspace()}),.1)
        self.assertTrue(all(job.done()for job in runtime.running.values()))
        self.assertNotIn('b',k.journal.event_records())
        self.assertFalse(k.journal.usage()['accounting_valid'])

    async def test_changed_replay_is_rejected_before_any_model_call(self):
        k=self.kernel();k.journal.intake(Event('a','a','Original'))
        with self.assertRaisesRegex(ValueError,'previously accepted'):
            await Runtime('superagent',k).run([Event('a','a','Changed')],{'a':DiagnosticWorkspace()})
        self.assertEqual(k.journal.usage()['calls'],[])

    async def test_benchmark_identifiers_are_opaque_in_model_messages(self):
        task='instance_repo-'+('a'*40)
        k=self.kernel()
        await Runtime('superagent',k).run([Event('request:'+task,'thread:'+task,'Fix the supplied public task',task_id=task)],{task:DiagnosticWorkspace()})
        with k.journal.db()as db:
            records=[json.loads(row[0]) for row in db.execute("SELECT payload FROM trace WHERE kind='model_request'")]
        self.assertTrue(records)
        self.assertTrue(all(task not in json.dumps(row['messages'])for row in records))
        self.assertIn(task,k.journal.event_records()['request:'+task].task_id)

    async def test_followup_arriving_during_final_response_is_not_lost(self):
        started,release=asyncio.Event(),asyncio.Event()
        class SlowWorker(DiagnosticModel):
            async def complete(self,messages,tools,*,role):
                if role=='worker' and not started.is_set():
                    started.set();await release.wait()
                return await super().complete(messages,tools,role=role)
        k=self.kernel(SlowWorker())
        async def inject():
            await started.wait()
            k.journal.assign(Event('u','a','update',task_id='a',kind='followup'),'a','worker:a','worker',subscribe=True)
            release.set()
        injector=asyncio.create_task(inject())
        rows=await Runtime('superagent',k).run([Event('a','a','A')],{'a':DiagnosticWorkspace()})
        await injector
        self.assertEqual(rows[0]['state'],'completed')
        self.assertTrue(any('update' in str(m) for m in k.journal.session('worker:a')[0]))
        self.assertEqual(len(k.journal.usage()['calls']),3)

    async def test_uncertain_tool_is_not_reexecuted_on_resume(self):
        k=self.kernel()
        k.journal.save('worker:a',[{'role':'system','content':'task'}],'tool_pending')
        with self.assertRaisesRegex(RuntimeError,'uncertain'):
            await k.work('a','instruction',DiagnosticWorkspace())

    async def test_completed_worker_reports_are_available_to_persistent_router(self):
        k=self.kernel()
        await Runtime('superagent',k).run([Event('a','a','A')],{'a':DiagnosticWorkspace()})
        history=k.journal.session('router')[0]
        report=json.loads(history[-1]['content'].split(': ',1)[1])
        self.assertEqual(report['state'],'completed')
        self.assertTrue(report['result'])

    async def test_restart_resumes_known_idle_session_and_refuses_uncertain_side_effect(self):
        k=self.kernel()
        e=Event('a','a','A');k.journal.intake(e);k.journal.assign(e,'a','worker:a','worker')
        k.journal.task_state('a','running');k.journal.save('worker:a',[{'role':'system','content':'Retained task'}])
        result=await Runtime('superagent',k).run([],{'a':DiagnosticWorkspace()})
        self.assertEqual(result[0]['state'],'completed')
        k.journal.task_state('a','running');k.journal.save('worker:a',[],state='tool_pending')
        with self.assertRaisesRegex(RuntimeError,'reconciliation'):
            await Runtime('superagent',k).run([],{'a':DiagnosticWorkspace()})

    async def test_truncated_model_output_keeps_known_token_charges(self):
        class Truncated(DiagnosticModel):
            async def complete(self,*args,**kw):
                return Reply({'role':'assistant','content':'partial'},Usage(30,8),'fixed','length')
        k=self.kernel(Truncated())
        with self.assertRaisesRegex(RuntimeError,'length'):
            await k.work('a','task',DiagnosticWorkspace())
        usage=k.journal.usage()
        self.assertTrue(usage['accounting_valid'])
        self.assertEqual(usage['input_tokens'],30)
        self.assertEqual(usage['output_tokens'],8)
        self.assertEqual(usage['uncertain_or_pending_call_count'],0)

    async def test_context_preflight_failure_does_not_reserve_or_bill_generation(self):
        class TooLong(DiagnosticModel):
            async def prepare(self,messages,tools):
                raise RuntimeError('Context limit reached before generation')
        k=self.kernel(TooLong())
        with self.assertRaisesRegex(RuntimeError,'before generation'):
            await k.work('a','task',DiagnosticWorkspace())
        self.assertEqual(k.journal.usage()['calls'],[])
        self.assertTrue(k.journal.usage()['accounting_valid'])

    async def test_tool_response_protocol_and_usage(self):
        class ToolModel(DiagnosticModel):
            async def complete(self,messages,tools,*,role):
                if messages[-1]['role']!='tool':
                    return Reply({'role':'assistant','content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'execute','arguments':'{"command":"test"}'}}]},Usage(5,5),'fixed')
                return Reply({'role':'assistant','content':'finished'},Usage(10,5),'fixed')
        class W:
            identity={'backend':'fixture'}
            async def execute(self,command,timeout_s):
                self.command=command;return {'stdout':'one test passed','returncode':0}
        k=self.kernel(ToolModel());w=W()
        self.assertEqual(await k.work('a','task',w),'finished');self.assertEqual(w.command,'test')
        self.assertEqual(k.journal.usage()['input_tokens'],15)


class PartialVerifierTests(unittest.TestCase):
    def test_empty_collection_with_syntax_failure_is_valid_code_failure_only(self):
        from unittest.mock import patch
        from osa_eval.swebench_pro import ProTask
        for diagnostic in ('SyntaxError: unexpected character after line continuation character',
                           'IndentationError: expected an indented block', ''):
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);(root/'tests').mkdir();(root/'tests/config.json').write_text(json.dumps({'fail_to_pass':['required']}))
                submitted=root/'model.patch';submitted.write_bytes(b'');output=root/'grade'
                class Workspace:
                    prefix=['unused-docker'];container='test';cwd='/app';identity={'image_id':'sha256:test'}
                    async def execute(self, command, timeout):
                        if command=='bash /tests/test.sh':
                            (output/'output.json').write_text('{"tests":[]}');(output/'reward.txt').write_text('0');(output/'run-script-stdout.txt').write_text(diagnostic)
                        return {'returncode':0,'stdout':'/app','stderr':''}
                    def stop(self): pass
                task=ProTask.__new__(ProTask);task.path=root;task.id='fixture';task.files={};task.config={'verifier':{'timeout_sec':1}};task.copy=lambda *args:None
                with patch('osa_eval.swebench_pro.subprocess.run',return_value=subprocess.CompletedProcess([],0)):
                    result=asyncio.run(task.grade(Workspace,submitted,output))
                self.assertEqual(result['valid'],bool(diagnostic))
                if diagnostic:self.assertFalse(result['success']);self.assertEqual(result['collected_tests'],0);self.assertEqual(result['missing_required_tests'],['required'])
    def test_partial_collection_distinguishes_toolchain_crash_from_test_failure(self):
        from unittest.mock import patch
        from osa_eval.swebench_pro import ProTask
        for crash in (None, '/usr/local/go/pkg/tool/linux_amd64/link: signal: segmentation fault',
                      'gcc: internal compiler error: Segmentation fault signal terminated program cc1'):
            fatal = crash is not None
            with self.subTest(compiler_crash=fatal), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'tests').mkdir()
                (root / 'tests/config.json').write_text(json.dumps({'fail_to_pass': ['required'], 'pass_to_pass': []}), encoding='utf-8')
                submitted = root / 'model.patch'; submitted.write_bytes(b'')
                output = root / 'grade'
                class Workspace:
                    prefix = ['unused-docker']; container = 'test'; cwd = '/app'; identity = {'image_id': 'sha256:test'}
                    stopped = False
                    async def execute(self, command, timeout):
                        if command == 'bash /tests/test.sh':
                            (output / 'output.json').write_text(json.dumps({'tests': [{'name': 'other', 'status': 'PASSED'}]}), encoding='utf-8')
                            (output / 'reward.txt').write_text('0', encoding='utf-8')
                            (output / 'run-script-stdout.txt').write_text('--- PASS: other (0.01s)', encoding='utf-8')
                            (output / 'run-script-stderr.txt').write_text(crash or '', encoding='utf-8')
                            return {'returncode': 1, 'stdout': '', 'stderr': ''}
                        return {'returncode': 0, 'stdout': '/app', 'stderr': ''}
                    def stop(self): self.stopped = True
                workspace = Workspace()
                task = ProTask.__new__(ProTask); task.path = root; task.id = 'fixture'; task.files = {}; task.config = {'verifier': {'timeout_sec': 1}}
                task.copy = lambda *args: None
                with patch('osa_eval.swebench_pro.subprocess.run', return_value=subprocess.CompletedProcess([], 0)):
                    result = asyncio.run(task.grade(lambda: workspace, submitted, output))
                self.assertTrue(workspace.stopped)
                if fatal:
                    self.assertFalse(result['valid']); self.assertIsNone(result['success'])
                    self.assertEqual(result['infrastructure_failure']['collected_tests_before_failure'], 1)
                else:
                    self.assertTrue(result['valid']); self.assertFalse(result['success'])


if __name__=='__main__':unittest.main()
