"""Read-only counterparts of the official Pro V2 history/leak checks."""
from __future__ import annotations

import json
import re
import shlex

from .contracts import canonical


PROBE = r'''
import json,subprocess,sys,pathlib,re,hashlib
fix,created=sys.argv[1],json.loads(sys.argv[2])
def git(*args):
 p=subprocess.run(['git','--no-optional-locks','-c','core.fsmonitor=false',*args],text=True,capture_output=True,timeout=240)
 return p.returncode,p.stdout,p.stderr
fix_code,fix_type,_=git('cat-file','-t',fix)
_,refs,_=git('for-each-ref','--format=%(refname) %(objectname)')
_,reflog,_=git('reflog','--format=%H')
_,stash,_=git('stash','list')
fsck_code,fsck,fsck_errors=git('fsck','--unreachable','--no-reflogs')
_,all_count,_=git('rev-list','--all','--count')
_,head_count,_=git('rev-list','HEAD','--count')
gitdir=pathlib.Path(git('rev-parse','--git-dir')[1].strip())
hooks=[p.name for p in(gitdir/'hooks').glob('*')if not p.name.endswith('.sample')]
metadata=[]
for name in ['ORIG_HEAD','FETCH_HEAD']:
 p=gitdir/name
 if not p.exists():continue
 raw=p.read_bytes();lines=raw.decode().splitlines();verified=True
 for line in lines:
  match=re.match(r'^([0-9a-f]{40})',line)
  shape=(bool(re.fullmatch(r'[0-9a-f]{40}',line)) if name=='ORIG_HEAD' else bool(re.fullmatch(r"[0-9a-f]{40}\t(?:not-for-merge)?\tbranch 'sanitized-history' of /tmp/hist\.bundle",line)))
  verified=verified and shape and match is not None and git('merge-base','--is-ancestor',match.group(1),'HEAD')[0]==0
 metadata.append({'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'verified_sanitized_ancestor_metadata':bool(verified)})
result={'fix_object_absent':fix_code!=0,'refs':refs.splitlines(),'reflog_count':len(reflog.splitlines()),'stash_count':len(stash.splitlines()),
 'unreachable_commits':sum('unreachable commit'in l for l in fsck.splitlines()),'fsck_returncode':fsck_code,'fsck_errors':fsck_errors[-2000:],
 'all_ref_commits':int(all_count),'head_commits':int(head_count),'hooks':hooks,
 'orig_or_fetch_head':metadata,'head_metadata_verified':all(x['verified_sanitized_ancestor_metadata']for x in metadata),
 'created_test_files_present':sum(pathlib.Path(p).exists()for p in created),'created_test_files_checked':len(created),
 'tests_directory_present':pathlib.Path('/tests').exists(),'solution_directory_present':pathlib.Path('/solution').exists()}
print(json.dumps(result))
'''


def created_paths(test_patch):
    lines = test_patch.splitlines()
    paths = [lines[i+1][6:] for i, line in enumerate(lines[:-1]) if line.startswith("--- /dev/null") and lines[i+1].startswith("+++ b/")]
    paths += [line[len("rename to "):] for line in lines if line.startswith("rename to ")]
    if any(path.startswith("/") or ".." in path.split("/") for path in paths):
        raise ValueError("Test patch contains a path outside the task repository")
    return sorted(set(paths))


def history_ok(result):
    return (result["fix_object_absent"] and result["reflog_count"] == result["stash_count"] == result["unreachable_commits"] == 0
            and result["fsck_returncode"] == 0 and result["all_ref_commits"] == result["head_commits"]
            and not result["hooks"] and result["head_metadata_verified"] and result["created_test_files_present"] == 0
            and not result["tests_directory_present"] and not result["solution_directory_present"])


async def probe_history(task, workspace):
    match = re.search(r"-([0-9a-f]{40})", task.id)
    if not match:
        raise ValueError("Official task ID does not identify its fixing commit")
    paths = created_paths((task.path / "tests/test_patch.patch").read_text(encoding="utf-8"))
    command = "python3 -c " + shlex.quote(PROBE) + " " + shlex.quote(match.group(1)) + " " + shlex.quote(canonical(paths))
    receipt = await workspace.execute(command, 300)
    if receipt["returncode"]:
        raise RuntimeError("History probe failed: " + receipt["stderr"][-2000:])
    result = json.loads(receipt["stdout"])
    if not history_ok(result):
        raise RuntimeError("History/leak gate failed: " + canonical(result))
    return result
