#!/usr/bin/env python3
"""Publish compact experiment metrics without puzzle rows or candidate programs."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
 result={'description':'Aggregate experiment results; raw competition data, detailed traces and third-party program rows are local-only.','gcd':{},'search':{},'factor':{}}
 for name,label in [('initial_gcd_50_results.json','initial_gcd_50'),('gcd_known_sample_20.json','runtime_gcd_20'),('gcd_known_sample_20_nonsmooth.json','runtime_gcd_20_nonsmooth')]:
  path=ROOT/name
  if path.exists():
   data=json.loads(path.read_text());result['gcd'][label]={k:data[k] for k in ('seed','sample_size','total_targets','summary','totals','non_smooth','puzzles_sha256') if k in data}
 for name in ['pilot_48','pilot_v196_24','pilot_132477_16','pilot_product_beam1','pilot_product_beam5','pilot_product_random12_beam1','pilot_product_random12_beam5','pilot_factor_joint']:
  path=ROOT/name/'report.json'
  if not path.exists():continue
  data=json.loads(path.read_text());rows=data.get('rows',data.get('results',[]));summary={k:data[k] for k in ('width','slack','per_target','rounds_per_arm','factor_group_cap','score','baseline_sha256','puzzles_sha256') if k in data}
  summary['puzzles']=len(rows);summary['rows']=[{k:r[k] for k in ('id','before','after','base','single','multi','best','stats','counts') if k in r} for r in rows]
  result['search'][name]=summary
 for name in ['pilot_factor_12','pilot_factor_deep']:
  path=ROOT/name/'wins.json'
  if not path.exists():continue
  data=json.loads(path.read_text());result['factor'][name]={k:data[k] for k in ('complete','parameters','rows','parent','source','native_source') if k in data}
 out=ROOT/'research_summary.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('wrote',out)
if __name__=='__main__':main()
