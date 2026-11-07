from pathlib import Path
import json, statistics, importlib.metadata, argparse, hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser()
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
data=json.loads(args.input.read_text())
out=args.output;out.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                     'svg.fonttype':'none','figure.dpi':140})
arms=[('single','Single','#595959'),('single_subagent','Single + Subagent','#009E73'),
      ('eager_delegation','Eager','#E69F00'),('router_worker','Router-Worker','#0072B2'),
      ('superagent','Super-agent','#CC79A7')]
fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
for ax,slots in zip(axes,[1,4]):
    for arm,label,color in arms:
        y=[statistics.mean(r['task_throughput_per_s']for r in data['capacity_cells']
               if r['architecture']==arm and r['slots']==slots and r['count']==n)for n in [1,4,8,16]]
        ax.plot([1,4,8,16],y,marker='o',label=label,color=color,lw=1.6,ms=4)
    ax.set(title=f'Common worker capacity: {slots}',xlabel='Simultaneous independent tasks',
           ylabel='Completed tasks / second',xticks=[1,4,8,16]);ax.grid(alpha=.2);ax.set_ylim(bottom=0)
axes[0].legend(fontsize=8,frameon=False)
fig.suptitle('Deterministic scheduling workload · 100 ms per task · mean of 3 repetitions',fontsize=11)
for ext in ['png','svg']:fig.savefig(out/('system-throughput.'+ext),dpi=180)
plt.close(fig)
variants=[('fresh','Fresh router','#0072B2'),('persistent','Persistent router','#E69F00'),
          ('persistent_subscription','Persistent + subscription','#009E73')]
fig,axes=plt.subplots(1,3,figsize=(12,3.5),layout='constrained')
metrics=[('router_fixture_calls','Router fixture calls'),('route_latency_ms_p95','Routing latency P95 (ms)'),
         ('router_context_characters','Total router input characters')]
for ax,(metric,ylabel)in zip(axes,metrics):
    for variant,label,color in variants:
        y=[statistics.mean(r[metric]for r in data['event_cells']if r['context_variant']==variant
                           and r['followups_per_task']==n)for n in [0,1,8]]
        ax.plot([0,1,8],y,marker='o',label=label,color=color,lw=1.7,ms=4)
    ax.set(xlabel='Follow-up events per task',ylabel=ylabel,xticks=[0,1,8]);ax.grid(alpha=.2);ax.set_ylim(bottom=0)
axes[0].legend(fontsize=8,frameon=False)
axes[2].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
fig.suptitle('Four tasks · equal work per event · zero model API calls',fontsize=11)
for ext in ['png','svg']:fig.savefig(out/('system-events.'+ext),dpi=180)
plt.close(fig)
(out/'PLOT_PROVENANCE.json').write_text(json.dumps({'matplotlib':importlib.metadata.version('matplotlib'),
    'source':'system303/RESULTS.json','source_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),'all_y_axes_start_at_zero':True,'replicates':3,'p95_curve':'mean of each repetition P95; not a pooled percentile',
    'actual_API_tokens':0,'context_characters_are_not_tokens':True},indent=2))
print('Saved two measured System Track figures')
