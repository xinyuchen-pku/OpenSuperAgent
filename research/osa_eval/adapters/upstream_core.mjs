// Execute the pinned upstream Engine directly. No production Sources or Channels are loaded.
// This adapter validates domain semantics; it does not reproduce the DSH host scheduler.
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';

const [checkoutArg, stateArg] = process.argv.slice(2);
if (!checkoutArg || !stateArg) throw new Error('Usage: upstream_core.mjs UPSTREAM_CHECKOUT STATE_JSON');
const checkout = resolve(checkoutArg), statePath = resolve(stateArg);
const expected = '6337fc823ce20251c8de8085948165c81aaa701e';
if (execFileSync('git', ['-C', checkout, 'rev-parse', 'HEAD'], {encoding:'utf8'}).trim() !== expected)
  throw new Error('Upstream commit does not match the source-fidelity lock');
execFileSync('git', ['-C', checkout, 'diff', '--no-ext-diff', '--no-textconv', '--quiet', 'HEAD', '--', 'src/core']);
const { Engine } = await import(pathToFileURL(resolve(checkout, 'src/core/engine.ts')).href);
const { MemoryRepositories } = await import(pathToFileURL(resolve(checkout, 'src/core/memory.ts')).href);
const repo = new MemoryRepositories();
const ids = new Set(), outbox = new Map();
let clock = '2026-11-02T00:00:00.000Z', effects = [], domainEvents = [];
if (existsSync(statePath)) {
  const state = JSON.parse(readFileSync(statePath, 'utf8'));
  if (state.commit !== expected) throw new Error('Snapshot belongs to a different upstream commit');
  clock = state.clock;
  for (const t of state.triggers) { ids.add(t.trigger.id); repo.triggers.save(t.trigger); if(t.disposition) repo.triggers.saveDisposition(t.trigger.id,t.disposition); }
  for (const t of state.threads) repo.threads.save(t);
  for (const t of state.tickets) repo.tickets.save(t);
  for (const d of state.decisions) repo.decisions.save(d);
  for (const message of state.outbox) outbox.set(message.id,message);
}
const policy = {
  version:'benchmark-explicit-v1', paused:false, evalTimeoutMs:60000,
  gate: t => t.human && t.actor.id === 'researcher'
    ? {admissible:true,strength:'explicit',basis:{via:'listed'}}
    : {admissible:false,reason:'benchmark gate'},
  revalidate: () => true, admitsInferred: () => false,
};
const engine = new Engine({repo, policy:()=>policy, scope:{scope:()=>({listened:true,observed:false})},
  assessor:{request:candidate=>effects.push({kind:'assess',candidate}),release:evalId=>effects.push({kind:'release',evalId})},
  executor:{start:(ticket,assignment)=>effects.push({kind:'start',ticket,assignment}),
    deliver:(ticket,assignment)=>effects.push({kind:'deliver',ticket,assignment}),
    stop:(ticket,assignment,reason)=>effects.push({kind:'stop',ticket,assignment,reason})},
  outbox:{send:message=>{if(!outbox.has(message.id))outbox.set(message.id,message)},
    status:id=>outbox.has(id)?'pending':undefined,withdraw:id=>outbox.delete(id)},
  now:()=>clock, emit:event=>domainEvents.push(event)});
function snapshot() {
  const threads=repo.threads.list();
  return {commit:expected,clock,triggers:[...ids].map(id=>({trigger:repo.triggers.get(id),disposition:repo.triggers.disposition(id)})),
    threads,tickets:repo.tickets.list(),decisions:threads.flatMap(t=>repo.decisions.byThread(t.key)),outbox:[...outbox.values()]};
}
const allowed = new Set(['evaluateDue','candidate','candidateDelivered','decide','assignmentStarted','inputsDelivered','inputsRead','turnEnded',
  'report','assignmentInterrupted','followForContext','handback','stopTicket','retryTicket','unsubscribe','attach','bindThread','threadClosed']);
for await (const line of createInterface({input:process.stdin,crlfDelay:Infinity})) {
  try {
    const request=JSON.parse(line); effects=[]; domainEvents=[];
    if(request.at)clock=request.at;
    let result;
    if(request.method==='receive') {
      const trigger=request.args[0];
      const previous=repo.triggers.get(trigger.id);
      if(previous && JSON.stringify(previous)!==JSON.stringify(trigger))throw new Error('Event id changed payload');
      result=engine.receive(trigger); ids.add(trigger.id);
    } else if(request.method==='snapshot') result=snapshot();
    else if(allowed.has(request.method))result=engine[request.method](...(request.args??[]));
    else throw new Error('Unsupported core command');
    mkdirSync(dirname(statePath),{recursive:true});
    writeFileSync(statePath+'.tmp',JSON.stringify(snapshot())); renameSync(statePath+'.tmp',statePath);
    process.stdout.write(JSON.stringify({ok:true,result:result??null,effects,events:domainEvents})+'\n');
  } catch(error) {process.stdout.write(JSON.stringify({ok:false,error:error.message})+'\n');}
}
