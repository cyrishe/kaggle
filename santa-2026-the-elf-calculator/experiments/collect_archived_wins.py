#!/usr/bin/env python3
"""Compare archived third-party per-puzzle programs against a fixed baseline."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from first_solver import validate
csv.field_size_limit(1000000)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--baseline',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 with (ROOT/'data/puzzles.csv').open(newline='') as f:puzzles={r['id']:r for r in csv.DictReader(f)}
 base=a.baseline or a.repo/'public-assisted/submission.csv'
 with base.open(newline='') as f: solutions={r['id']:json.loads(r['program']) for r in csv.DictReader(f)}
 ledger={};files=[];errors=[]
 for path in sorted((a.repo/'collaboration').rglob('*wins.csv')):
  try:
   with path.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
   if not rows or not {'id','program'} <= rows[0].keys():continue
   files.append({'path':str(path.relative_to(a.repo)),'sha256':sha(path)})
   for r in rows:
    ident=r['id']; prog=json.loads(r['program'])
    if ident not in puzzles or len(prog)>=len(solutions[ident]): continue
    validate(puzzles[ident],prog)
    ledger[ident]={'source':str(path.relative_to(a.repo)),'file_sha256':sha(path),'previous':len(solutions[ident]),'steps':len(prog)};solutions[ident]=prog
  except (ValueError,KeyError,TypeError,csv.Error) as e: errors.append({'path':str(path.relative_to(a.repo)),'error':str(e)})
 for ident,p in puzzles.items():validate(p,solutions[ident])
 a.out.mkdir(parents=True,exist_ok=True);dest=a.out/'candidate.csv'
 with dest.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['id','program']);w.writerows((i,json.dumps(solutions[i],separators=(',',':'))) for i in sorted(solutions))
 report={'baseline_sha256':sha(base),'puzzles_sha256':sha(ROOT/'data/puzzles.csv'),'result_sha256':sha(dest),'score':sum(map(len,solutions.values())),'wins':ledger,'sources_inspected':files,'errors':errors}
 (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print('score',report['score'],'wins',len(ledger),'errors',len(errors));print(json.dumps(ledger,indent=2))
if __name__=='__main__':main()
