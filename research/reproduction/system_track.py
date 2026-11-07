"""Measured deterministic System Track. Zero model API calls; no coding-success claims."""
from pathlib import Path
import asyncio, hashlib, json, math, os, re, sqlite3, subprocess, sys, time

SOURCE=Path(os.environ.get('OSA_SOURCE',str(Path(__file__).resolve().parents[1])))
sys.path.insert(0,str(SOURCE))
from osa_eval.contracts import Event, Limits, Reply, Usage, canonical
from osa_eval.journal import Journal
from osa_eval.kernel import Kernel
from osa_eval.runtime import Runtime, ARCHITECTURES

PLAN={'purpose':'System mechanisms only; deterministic delayed work, not benchmark success',
      'actual_api_calls':0,'actual_api_tokens':0,'load_sizes':[1,4,8,16],'slot_ceilings':[1,4],
      'repetitions':3,'router_delay_s':.01,'worker_response_delay_s':.005,'work_delay_s':.1,
      'followups_per_task':[0,1,8],'router_context_variants':['fresh','persistent','persistent_subscription'],
      'event_tasks':4,'event_burst_start_s':.4,'event_spacing_s':.002,
      'recovery':'separate process restart at acknowledged idle checkpoint; replay plus appended events',
      'uncertain_side_effects':'must refuse automatic replay; no arbitrary exactly-once crash claim',
      'worker_policy':'delegate in optional baseline; fixed exogenous decisions, not learned routing',
      'work_accounting':'Exactly one100ms work unit per distinct received WORK_EVENT marker; all markers must appear in worker context and final tool receipts',
      'supersedes':'system270 event workload allowed coalesced inputs to induce different work counts; retain original evidence but use this equal-work workload for final event comparisons'}


class DeterministicModel:
    identity={'model':'fixed-system-workload','real_model':False}
    def __init__(self,journal):self.journal=journal
    async def complete(self,messages,tools,role):
        router=tools[0]['function']['name']=='route'
        self.journal.trace('fixture_request',router=router,context_characters=len(canonical(messages)))
        await asyncio.sleep(PLAN['router_delay_s']if router else PLAN['worker_response_delay_s'])
        if router:name,args='route',{'action':'delegate'}
        else:
            requested=set()
            completed=set()
            for message in messages:
                if message['role']=='user':requested.update(re.findall(r'WORK_EVENT=([a-zA-Z0-9:_-]+)',message.get('content')or''))
                if message['role']=='tool':
                    output=json.loads(message['content'])
                    if output.get('stdout','').startswith('completed:'):completed.add(output['stdout'].removeprefix('completed:'))
            pending=sorted(requested-completed)
            if not pending:return Reply({'role':'assistant','content':'Fixed work completed'},Usage(0,0),self.identity['model'])
            name,args='execute',{'command':'fixed_work_unit:'+pending[0]}
        return Reply({'role':'assistant','content':None,'tool_calls':[{'id':'fixed-call','type':'function',
                      'function':{'name':name,'arguments':canonical(args)}}]},Usage(0,0),self.identity['model'],'tool_calls')


class FixedWork:
    identity={'backend':'deterministic delayed work','benchmark':False}
    def __init__(self,journal,task):self.journal,self.task=journal,task
    async def execute(self,command,timeout_s):
        assert command.startswith('fixed_work_unit:')
        marker=command.removeprefix('fixed_work_unit:')
        self.journal.trace('fixed_work_started',task_id=self.task,work_event=marker)
        await asyncio.sleep(PLAN['work_delay_s'])
        self.journal.trace('fixed_work_finished',task_id=self.task,work_event=marker)
        return dict(stdout='completed:'+marker,stderr='',returncode=0)


def traces(journal):
    with journal.db()as db:return [{**json.loads(r['payload']),'at':r['at'],'kind':r['kind']}for r in db.execute('SELECT * FROM trace ORDER BY seq')]


def percentile(values,q):
    if not values:return None
    values=sorted(values);return values[max(0,math.ceil(q*len(values))-1)]


async def cell(out,architecture,count,slots,followups=0,subscriptions=True,events=None,identity=None):
    limits=Limits(slots=slots,model_concurrency=4,token_budget=1000000,request_token_reservation=100,
                  max_steps=100,tool_timeout_s=5,task_timeout_s=30)
    identity=identity or {'architecture':architecture,'count':count,'slots':slots,'followups':followups,
                          'subscriptions':subscriptions,'plan':PLAN}
    j=Journal(out/'run.sqlite3',token_budget=limits.token_budget,identity=identity)
    if events is None:
        events=[Event('request:'+str(i),'thread:'+str(i),'WORK_EVENT=request:'+str(i),task_id=str(i))for i in range(count)]
        events += [Event('event:'+str(k)+':'+str(i),'thread:'+str(i),'WORK_EVENT=event:'+str(k)+':'+str(i),
                        PLAN['event_burst_start_s']+k*PLAN['event_spacing_s'],task_id=str(i),kind='followup')
                   for k in range(followups)for i in range(count)]
    model=DeterministicModel(j);started=time.monotonic()
    tasks=await Runtime(architecture,Kernel(model,j,limits),subscriptions=subscriptions).run(events,
                  {str(i):FixedWork(j,str(i))for i in range(count)})
    elapsed=time.monotonic()-started;j.export(out);rows=traces(j)
    assert all(x['state']=='completed'for x in tasks)
    with j.db()as db:
        unread=db.execute('SELECT COUNT(*) FROM inputs WHERE read=0').fetchone()[0]
        received=db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    assert unread==0 and received==len(events)
    active=maximum=0
    for r in rows:
        if r['kind']=='fixed_work_started':active+=1;maximum=max(maximum,active)
        elif r['kind']=='fixed_work_finished':active-=1
    assert active==0 and maximum<=slots
    finished=[r['work_event']for r in rows if r['kind']=='fixed_work_finished'];assert len(finished)==len(events)and len(set(finished))==len(events)
    intake={r['id']:r['at']for r in rows if r['kind']=='event_received'}
    latency=[(r['at']-intake[r['event_id']])*1000 for r in rows if r['kind']=='task_assigned']
    router=[r for r in rows if r['kind']=='fixture_request'and r['router']]
    result={'architecture':architecture,'count':count,'slots':slots,'followups_per_task':followups,
            'subscriptions':subscriptions,'wall_s':elapsed,'completed_tasks':len(tasks),
            'task_throughput_per_s':len(tasks)/elapsed,'max_parallel_fixed_work':maximum,
            'route_latency_ms_p50':percentile(latency,.5),'route_latency_ms_p95':percentile(latency,.95),
            'router_fixture_calls':len(router),'router_context_characters':sum(r['context_characters']for r in router),
            'actual_api_calls':0,'actual_api_tokens':0,'delivered_events':received,'unread_inputs':unread,
            'work_units':sum(r['kind']=='fixed_work_finished'for r in rows),'benchmark_success_rate':None}
    (out/'system-result.json').write_text(canonical(result));return result


def restart_child(root,phase):
    root=Path(root);identity={'restart':'system303','plan':PLAN}
    requests=[Event('request:'+str(i),'thread:'+str(i),'WORK_EVENT=request:'+str(i),task_id=str(i))for i in range(2)]
    updates=[Event('update:'+str(i),'thread:'+str(i),'WORK_EVENT=update:'+str(i),task_id=str(i),kind='followup')for i in range(2)]
    return asyncio.run(cell(root,'superagent',2,2,events=requests if phase=='first'else requests+updates,identity=identity))


async def main(output):
    output.mkdir(exist_ok=False,parents=True);(output/'PREREGISTRATION.json').write_text(canonical(PLAN))
    rows=[]
    for slots in PLAN['slot_ceilings']:
        for count in PLAN['load_sizes']:
            for rep in range(PLAN['repetitions']):
                # Rotate execution order to limit wall-clock drift, with no outcome-based ordering.
                arms=list(ARCHITECTURES);arms=arms[rep:]+arms[:rep]
                for arm in arms:rows.append(await cell(output/f'capacity-{slots}-{count}-{rep}-{arm}',arm,count,slots))
    event_rows=[]
    for followups in PLAN['followups_per_task']:
        for rep in range(PLAN['repetitions']):
            for label,arm,subs in [('fresh','router_worker',False),('persistent','superagent',False),('persistent_subscription','superagent',True)]:
                result=await cell(output/f'events-{followups}-{rep}-{label}',arm,4,4,followups,subs)
                result.update(context_variant=label,repetition=rep);event_rows.append(result)
    recovery=output/'restart'
    for phase in ['first','resume']:
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restart-child',str(recovery),phase],capture_output=True,text=True,timeout=30)
        assert p.returncode==0,p.stderr
        (output/('restart-'+phase+'.json')).write_text(p.stdout)
    r=json.loads((recovery/'system-result.json').read_text());assert r['delivered_events']==4 and r['work_units']==4 and r['unread_inputs']==0
    j=Journal(output/'uncertain.sqlite3',token_budget=1000000,identity={'uncertain':True});e=Event('uncertain','thread','Work',task_id='0')
    j.intake(e);j.assign(e,'0','worker:0','worker');j.task_state('0','running');j.save('worker:0',[{'role':'system','content':'preserved'}],'tool_pending')
    try:
        await Runtime('superagent',Kernel(DeterministicModel(j),j,Limits())).run([e],{'0':FixedWork(j,'0')})
        raise AssertionError('Uncertain tool was replayed')
    except RuntimeError as error:assert 'explicit reconciliation'in str(error)
    final={'scope':'deterministic system mechanisms; no model capability claims','actual_api_calls':0,'actual_api_tokens':0,
           'capacity_cells':rows,'event_cells':event_rows,'restart':r,'uncertain_replay_refused':True,
           'source_manifest_sha256':hashlib.sha256((SOURCE/'SOURCE_MANIFEST.json').read_bytes()).hexdigest()}
    (output/'RESULTS.json').write_text(json.dumps(final,indent=2));print(json.dumps({'passed':True,'capacity_cells':len(rows),'event_cells':len(event_rows),'actual_api_calls':0}))


if __name__=='__main__':
    if sys.argv[1]=='--restart-child':print(canonical(restart_child(sys.argv[2],sys.argv[3])))
    else:asyncio.run(main(Path(sys.argv[1])))
