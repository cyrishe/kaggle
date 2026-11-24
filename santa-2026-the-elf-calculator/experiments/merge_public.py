#!/usr/bin/env python3
"""Choose validated shorter rows from public portfolios, preserving provenance."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from first_solver import validate
csv.field_size_limit(1_000_000)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('sources',nargs='+',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 with (ROOT/'data/puzzles.csv').open(newline='') as f:puzzles={r['id']:r for r in csv.DictReader(f)}
 choices={};origins={}
 for path in args.sources:
  source_hash=digest(path);seen=set()
  with path.open(newline='',encoding='utf-8-sig') as f:
   for row in csv.DictReader(f):
    ident=row['id']
    if ident in seen or ident not in puzzles:raise ValueError(f'duplicate or unknown ID in {path}: {ident}')
    seen.add(ident);program=json.loads(row['program']);validate(puzzles[ident],program)
    if ident not in choices or len(program)<len(choices[ident]):
     choices[ident]=program;origins[ident]={'path':str(path),'sha256':source_hash,'credit':row.get('source','See associated origins.csv and NOTICE')}
 if choices.keys()!=puzzles.keys():raise ValueError('incomplete portfolio')
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['id','program']);writer.writerows((k,json.dumps(choices[k],separators=(',',':'))) for k in sorted(choices))
 metadata={'score':sum(map(len,choices.values())),'output_sha256':digest(args.output),'puzzles_sha256':digest(ROOT/'data/puzzles.csv'),'sources':[{'path':str(p),'sha256':digest(p)} for p in args.sources],'origins':origins}
 args.output.with_suffix('.origins.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n');print(metadata['score'],metadata['output_sha256'])
if __name__=='__main__':main()
