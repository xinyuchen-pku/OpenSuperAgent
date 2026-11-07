"""Scientific figures from accepted source022 runs only; no placeholder points."""
from pathlib import Path
import argparse,json,collections,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ARMS=['single','single_subagent','eager_delegation','router_worker','superagent']
LABELS=['Single','Single + Subagent','Eager Delegation','Router-Worker','Super-agent']
COLORS=['#555555','#0072B2','#E69F00','#009E73','#9B59B6']

def plot_timeline(batches,output):
 # Actual lock-acquisition/release intervals establish execution overlap. Queued
 # worker-start events are deliberately not used as the beginning of execution.
 fig,axes=plt.subplots(5,1,figsize=(9,6.5),sharex=True,layout='constrained')
 parent=Path(__file__).resolve().parent;matrix=parent/'reproduction/m2-matrix.json'
 if not matrix.is_file():matrix=parent.parent/'reproduction/m2-matrix.json'
 task_ids=json.loads(matrix.read_text())['task_ids']
 task_colors=['#0072B2','#E69F00','#009E73','#CC79A7'];task_names=['Teleport 1','Teleport 2','qutebrowser','OpenLibrary']
 for ax,arm,label in zip(axes,ARMS,LABELS):
  batch=next(x for x in batches if x['section']=='primary'and x['architecture']==arm and x['seed']==20261102)
  for row in batch['session_windows']:
   i=task_ids.index(row['task_id']);ax.broken_barh([(row['start_s']/60,(row['end_s']-row['start_s'])/60)],(i-.35,.7),facecolors=task_colors[i])
  ax.set_yticks(range(4),['1','2','3','4']);ax.set_ylim(3.6,-.6);ax.set_ylabel(label,rotation=0,ha='right',va='center');ax.grid(axis='x',alpha=.2)
 axes[-1].set_xlabel('Agent time since concurrent task arrival (minutes)');axes[0].set_title('Measured Active Sessions, Seed 20261102')
 handles=[Line2D([],[],color=c,linewidth=6,label=n)for c,n in zip(task_colors,task_names)];fig.legend(handles=handles,loc='outside lower center',ncol=4,frameon=False);fig.savefig(output/'active-session-timeline.png',bbox_inches='tight');fig.savefig(output/'active-session-timeline.svg',bbox_inches='tight');plt.close(fig)

def main():
 p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--first-block-only',action='store_true');a=p.parse_args();data=json.loads(a.summary.read_text(encoding='utf-8'));batches=data['batches']
 if a.first_block_only:
  first=[x for x in batches if x['section']=='primary'and x['seed']==20261102];assert len(first)==5 and {x['architecture']for x in first}==set(ARMS);a.output.mkdir(parents=True,exist_ok=False);plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180});plot_timeline(first,a.output);print(json.dumps({'figures':1,'first_seed_grades':20,'final_concurrency_curves_generated':False}));return
 assert data['accepted_primary_grades']==60 and data['accepted_secondary_grades']==20,'All80 accepted grades are required for paired final figures';assert len(data['cases'])==80;a.output.mkdir(parents=True,exist_ok=False)
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
 pairs=[];pooled=[]
 for arm in ARMS:
  serial=[x for x in batches if x['section']=='secondary'and x['architecture']==arm];parallel=[x for x in batches if x['section']=='primary'and x['architecture']==arm];seed1=[x for x in parallel if x['seed']==20261102];assert len(serial)==4 and len(parallel)==3 and len(seed1)==1
  def aggregate(rows,c):
   tasks=sum(x['tasks']for x in rows);success=sum(x['successes']for x in rows);wall=sum(x['agent_wall_s']for x in rows);tokens=sum(x['actual_api_tokens']for x in rows)
   return {'architecture':arm,'concurrency':c,'tasks':tasks,'successes':success,'success_rate':success/tasks,'agent_wall_s':wall,'actual_api_tokens':tokens,'tokens_per_task_millions':tokens/tasks/1e6,'submitted_patches_per_hour':tasks*3600/wall,'successful_tasks_per_hour':success*3600/wall,'seeds':sorted({x['seed']for x in rows})}
  pairs.extend([aggregate(serial,1),aggregate(seed1,4)]);pooled.extend([aggregate(serial,1),aggregate(parallel,4)])
 (a.output/'plotted-values.json').write_text(json.dumps({'paired_seed20261102':pairs,'pooled':pooled,'infrastructure_exclusions':data.get('infrastructure_exclusions',[]),'wall_time_definition':'Agent batch clock; sum separate one-task clocks for concurrency1; official grading excluded','single_task_reference_protocol':'Four fresh independent runs per architecture; session state resets between tasks. The four-task point shares one architecture instance. Load and session boundary change together; descriptive reference, not an isolated causal estimate of concurrency.','token_cost_definition':'Actual API input plus output tokens, including coordinator calls; no monetary price assumed'},indent=2),encoding='utf-8')
 fig,axes=plt.subplots(1,5,figsize=(11,3.4),sharey=True,layout='constrained')
 for ax,arm,label,color,marker in zip(axes,ARMS,LABELS,COLORS,['o','s','^','D','v']):
  rows=[x for x in pairs if x['architecture']==arm];ax.plot([x['concurrency']for x in rows],[100*x['success_rate']for x in rows],color=color,marker=marker,markersize=8,markerfacecolor='none',linewidth=1.4)
  for row in rows:ax.annotate(f"{row['successes']}/{row['tasks']}",(row['concurrency'],100*row['success_rate']),xytext=(0,9),textcoords='offset points',ha='center',fontsize=9)
  ax.set(xticks=[1,4],yticks=[0,25,50,75,100],ylim=(-5,110),xlim=(.65,4.35),title=label);ax.title.set_fontsize(10);ax.grid(axis='y',alpha=.2)
 axes[0].set_ylabel('Official success rate (%)');fig.supxlabel('Simultaneously arriving tasks');fig.suptitle('Success Rate vs. Concurrency');fig.text(.08,-.12,'Same 4 tasks, seed 20261102. Only loads 1 and 4 measured.\n1 = four fresh single-task runs; 4 = one shared four-task batch. Session boundaries also differ.',fontsize=10)
 fig.savefig(a.output/'success-vs-concurrency.png',bbox_inches='tight');fig.savefig(a.output/'success-vs-concurrency.svg',bbox_inches='tight');plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout='constrained')
 for arm,label,color in zip(ARMS,LABELS,COLORS):
  for ax,metric in zip(axes,['submitted_patches_per_hour','successful_tasks_per_hour']):
   for row in [x for x in batches if x['section']=='primary'and x['architecture']==arm]:ax.scatter(row['actual_api_tokens']/row['tasks']/1e6,row[metric],s=20,color=color,alpha=.35)
   for row in [x for x in pairs if x['architecture']==arm]:ax.scatter(row['tokens_per_task_millions'],row[metric],s=80,color=color,marker='o'if row['concurrency']==4 else'^',facecolors=color if row['concurrency']==4 else'none',linewidths=1.4)
  axes[0].scatter([],[],label=label,color=color,s=40)
 axes[0].set_ylabel('Submitted patches / agent hour');axes[1].set_ylabel('Successful tasks / agent hour')
 for ax in axes:ax.set_xlabel('Actual API tokens / offered task (millions)');ax.grid(alpha=.2);ax.set_ylim(bottom=-.1)
 axes[0].legend(frameon=False,fontsize=10);fig.suptitle('Throughput vs. Token Cost');fig.text(.12,-.16,'Paired seed 20261102: filled circles = load 4; open triangles = single-task reference.\nFaint dots show all 3 individual load-4 seeds. One-task points sum four fresh runs;\nthe four-task batch shares session state within its architecture.',fontsize=10);fig.savefig(a.output/'throughput-vs-tokens.png',bbox_inches='tight');fig.savefig(a.output/'throughput-vs-tokens.svg',bbox_inches='tight');plt.close(fig)
 fields=['architecture','concurrency','tasks','successes','success_rate','agent_wall_s','actual_api_tokens','tokens_per_task_millions','submitted_patches_per_hour','successful_tasks_per_hour','seeds']
 with(a.output/'pooled-results.csv').open('w',encoding='utf-8',newline='')as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(pooled)
 plot_timeline(batches,a.output)
 print(json.dumps({'figures':3,'paired_cases':40,'all_accepted_cases':80,'output':str(a.output)}))

if __name__=='__main__':main()
