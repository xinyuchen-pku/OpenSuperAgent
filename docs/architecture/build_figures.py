"""Render the architecture diagrams and a recorded mechanism replay."""

import argparse
import hashlib
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from PIL import Image


HERE = Path(__file__).resolve().parent
INK = '#10243a'
MUTED = '#496075'
PAPER = '#f6f9fc'
ROUTER = '#2152a1'
WORKER = '#087264'
EVENT = '#a95a0b'
EDGE = '#cbd8e4'
PALE = {ROUTER: '#e7efff', WORKER: '#e3f4ef', EVENT: '#fff1d9', MUTED: '#eef3f8'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'path', 'svg.hashsalt': 'osa-v02'})


def canvas(width, height, title, subtitle):
    fig = plt.figure(figsize=(width, height), facecolor=PAPER)
    ax = fig.add_axes((0, 0, 1, 1), xlim=(0, width), ylim=(0, height))
    ax.axis('off')
    ax.text(.38, height-.38, title, color=INK, fontsize=22, fontweight='bold', va='top')
    ax.text(.4, height-.9, subtitle, color=MUTED, fontsize=10.7, va='top')
    return fig, ax


def card(ax, x, y, width, height, title, detail='', color=MUTED):
    rect = FancyBboxPatch((x, y), width, height, boxstyle='round,pad=0,rounding_size=.12',
                          linewidth=1.0, edgecolor=color, facecolor=PALE[color], zorder=3)
    ax.add_patch(rect)
    ax.text(x+.18, y+height-.16, title, va='top', color=color, fontweight='bold', fontsize=12, zorder=4)
    if detail:
        ax.text(x+.18, y+.15, detail, va='bottom', color=INK, fontsize=9.2, zorder=4)


def arrow(ax, start, end, color=MUTED, dashed=False, curve=0):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=13, linewidth=1.6,
                                color=color, linestyle='--' if dashed else '-',
                                connectionstyle=f'arc3,rad={curve}', shrinkA=1, shrinkB=1, zorder=2))


def save(fig, name):
    fig.savefig(HERE / f'{name}.png', dpi=150)
    path = HERE / f'{name}.svg'
    fig.savefig(path, metadata={'Date': None})
    path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines()) + '\n',
                    encoding='utf-8', newline='\n')
    plt.close(fig)


def overview():
    fig, ax = canvas(12, 5.45, 'The Super-agent task lifecycle',
                     'OpenSuperAgent research runtime  /  task-level coordination')
    card(ax, .4, 3.38, 2.2, .76, 'Incoming request', 'Task and thread identity', EVENT)
    card(ax, 3.06, 3.38, 2.38, .76, 'Persistent Router', 'Retained session history', ROUTER)
    card(ax, 5.93, 3.38, 2.55, .76, 'Task journal + queue', 'Durable state, bounded slots', ROUTER)
    card(ax, 9.02, 3.55, 2.56, .76, 'Worker A', 'Session + isolated workspace', WORKER)
    card(ax, 9.02, 2.48, 2.56, .76, 'Worker B', 'Session + isolated workspace', WORKER)
    card(ax, .4, 2.08, 2.2, .76, 'Follow-up event', 'A known thread', EVENT)
    card(ax, 3.06, 2.08, 2.38, .76, 'Thread subscription', 'Match the existing task', EVENT)
    card(ax, 5.93, 1.1, 2.55, .76, 'Worker reports', 'Task status and completion', WORKER)
    card(ax, 9.02, 1.1, 2.56, .76, 'Benchmark grading', 'Captured artifact in clean env', MUTED)
    arrow(ax, (2.6, 3.76), (3.06, 3.76))
    arrow(ax, (5.44, 3.76), (5.93, 3.76))
    arrow(ax, (8.48, 3.78), (9.02, 3.94), WORKER)
    arrow(ax, (8.48, 3.52), (9.02, 2.86), WORKER)
    arrow(ax, (2.6, 2.46), (3.06, 2.46), EVENT, dashed=True)
    arrow(ax, (5.44, 2.46), (9.02, 2.68), EVENT, dashed=True)
    arrow(ax, (10.3, 2.48), (10.3, 1.86), WORKER)
    arrow(ax, (9.16, 2.48), (8.14, 1.86), WORKER)
    arrow(ax, (6.6, 1.86), (4.7, 3.38), ROUTER, curve=.39)
    ax.text(.4, .62, 'SOLID  Assignment and result flow', color=MUTED, fontsize=9.6)
    ax.text(3.93, .62, 'DASHED  Subscribed event delivery', color=EVENT, fontsize=9.6)
    ax.text(.4, .28, 'Partial coverage  Safe checkpoint recovery and benchmark-specific integration', color=INK, fontsize=9.6)
    ax.text(7.02, .28, 'Planned  Full DSH, Watchdog, recursive delegation', color=MUTED, fontsize=9.1)
    save(fig, 'overview')


def comparison():
    fig, ax = canvas(12, 5.75, 'Where the five schedulers differ',
                     'Stage 2 controlled arms  /  the same coding Worker and complete-task budget')
    rows = [
        ('Single', 'One main execution at a time', 'No Router', 'No direct event delivery'),
        ('Single + Subagent', 'Main chooses self or delegate', 'Fresh main routing', 'No direct event delivery'),
        ('Eager Delegation', 'Delegate each supplied task', 'Fresh main routing', 'No direct event delivery'),
        ('Router–Worker', 'Router assigns separate Workers', 'Fresh Router per event', 'Routed through coordinator'),
        ('Super-agent', 'Router assigns separate Workers', 'Persistent Router history', 'Direct delivery to subscribers'),
    ]
    xs = [.55, 3.03, 6.53, 9.02]
    for x, label in zip(xs, ['CONDITION', 'TASK EXECUTION', 'COORDINATION STATE', 'FOLLOW-UP EVENTS']):
        ax.text(x, 4.31, label, fontsize=9, fontweight='bold', color=MUTED)
    for index, row in enumerate(rows):
        y = 3.92-index*.67
        ax.add_patch(FancyBboxPatch((.4, y-.30), 11.2, .57, boxstyle='round,pad=0,rounding_size=.09',
                                   facecolor=PALE[ROUTER] if index == 4 else '#ffffff', edgecolor=EDGE, linewidth=.8))
        for col, (x, label) in enumerate(zip(xs, row)):
            ax.text(x, y, label, va='center', color=[INK, WORKER, ROUTER, EVENT][col],
                    fontsize=10.2 if col else 11.4, fontweight='bold' if col == 0 or index == 4 else 'normal')
    ax.text(.4, .50, 'Eager delegates supplied tasks in parallel. Task-internal recursive decomposition is planned.',
            fontsize=10, color=MUTED)
    save(fig, 'comparison')


def capture(directory):
    trace = directory / 'trace.jsonl'
    receipt = json.loads((directory / 'receipt.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(trace.read_bytes()).hexdigest() == receipt['trace_sha256']
    wanted = {'run_started', 'run_finished', 'event_received', 'task_assigned', 'worker_started',
              'worker_slot_released', 'subscription_fanout', 'completion_notification',
              'model_request', 'model_response'}
    records = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    origin = records[0]['at']
    events = []
    for row in records:
        payload = row['payload']
        is_model = row['kind'] in {'model_request', 'model_response'}
        if row['kind'] in wanted and (not is_model or payload.get('role') == 'router'):
            events.append(dict(seq=row['seq'], seconds=round(row['at']-origin, 6), kind=row['kind'],
                               **{k: payload[k] for k in ('task_id', 'id', 'event_id', 'tasks', 'call_id') if k in payload}))
    out = dict(source_trace_sha256=receipt['trace_sha256'], source_manifest_sha256=receipt['source_manifest_sha256'],
               scope=receipt['scope'], actual_api_calls=receipt['actual_api_calls'],
               distinct_processes=len({p['pid'] for p in receipt['phases']}),
               phases=[p['result'] for p in receipt['phases']], events=events)
    (HERE / 'demo-trace.json').write_text(json.dumps(out, indent=2)+'\n', encoding='utf-8', newline='\n')


def timeline(data, stage=3):
    fig, ax = canvas(12, 4.65, 'Two workers, one persisted journal',
                     'Recorded deterministic run  /  0 model API calls  /  timestamps from the journal')
    events = data['events']
    start, restart = [r['seconds'] for r in events if r['kind'] == 'run_started']
    checkpoint, finish = [r['seconds'] for r in events if r['kind'] == 'run_finished']
    positions = {'0': 1.86, '1': 1.21}
    cut = [min(r['seconds'] for r in events if r['kind'] == 'worker_started'), checkpoint,
           max(r['seconds'] for r in events if r['kind'] == 'subscription_fanout'), finish][stage]
    x = lambda t: 1.88 + 9.35*(t-start)/(finish-start)
    ax.axvspan(x(checkpoint), x(restart), ymin=.19, ymax=.75, color='#e8eef5')
    ax.text((x(checkpoint)+x(restart))/2, 3.33, 'Process restart', color=MUTED, ha='center', fontsize=9)
    ax.text(.4, 3.02, 'Events', color=EVENT, fontsize=11, fontweight='bold', va='center')
    ax.text(.4, 2.48, 'Router fixture', color=ROUTER, fontsize=11, fontweight='bold', va='center')
    ax.hlines(2.48, x(start), x(finish), color=EDGE, linewidth=1)
    for key, y in positions.items():
        ax.text(.4, y, f'Worker {"AB"[int(key)]}', color=WORKER, va='center', fontsize=11, fontweight='bold')
        ax.hlines(y, x(start), x(finish), color=EDGE, linewidth=1)
    active, router = {}, {}
    for row in events:
        t, kind = row['seconds'], row['kind']
        if kind == 'event_received' and t <= cut:
            ax.scatter(x(t), 3.02, s=46, marker='D', color=EVENT, zorder=4)
        if kind == 'subscription_fanout' and t <= cut:
            arrow(ax, (x(t), 2.94), (x(t)+.03, positions[row['tasks'][0]]+.1), EVENT, dashed=True)
        if kind == 'model_request':
            router[row['call_id']] = t
        if kind == 'model_response':
            route_start = router.pop(row['call_id'])
            if route_start <= cut:
                ax.plot([x(route_start), x(min(t, cut))], [2.48]*2, color=ROUTER,
                        linewidth=6, solid_capstyle='round', zorder=3)
        if kind == 'worker_started':
            active[row['task_id']] = t
        if kind == 'worker_slot_released':
            start_work = active.pop(row['task_id'])
            if start_work <= cut:
                ax.plot([x(start_work), x(min(t, cut))], [positions[row['task_id']]]*2,
                        color=WORKER, linewidth=8, solid_capstyle='round', zorder=3)
    ax.text(x(start), .77, '0 s', color=MUTED, fontsize=9)
    ax.text(x(finish), .77, f'{finish-start:.2f} s', color=MUTED, fontsize=9, ha='right')
    messages = ['1 / Two requests arrive and the Router assigns them.',
                '2 / Both Workers run and reach a saved idle checkpoint.',
                '3 / A second process delivers follow-ups via saved subscriptions.',
                '4 / Both Workers complete their follow-ups. Router fixture calls stay at two.']
    ax.text(.4, .30, messages[stage], color=INK, fontsize=11)
    return fig


def replay(data):
    frames = []
    for stage in range(4):
        fig = timeline(data, stage)
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=90)
        with Image.open(buffer) as frame:
            frames.append(frame.convert('RGB'))
        plt.close(fig)
    frames[0].save(HERE / 'event-demo.gif', save_all=True, append_images=frames[1:],
                   duration=[8000]*4, loop=0, optimize=False, disposal=1)
    with Image.open(HERE / 'event-demo.gif') as encoded:
        assert encoded.n_frames == 4
        for index in range(encoded.n_frames):
            encoded.seek(index)
            encoded.load()
            assert encoded.info['duration'] == 8000


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, help='Use the trace from a fresh run_demo.py invocation')
    args = parser.parse_args()
    if args.capture:
        capture(args.capture)
    data = json.loads((HERE/'demo-trace.json').read_text(encoding='utf-8'))
    overview()
    comparison()
    save(timeline(data), 'event-timeline')
    replay(data)
