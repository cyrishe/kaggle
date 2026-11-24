#!/usr/bin/env python3
"""Factor puzzle values and inspect shared divisors in a real baseline trace."""
import argparse,csv,hashlib,itertools,json,math
from collections import Counter
from pathlib import Path
import sympy
ROOT=Path(__file__).resolve().parents[1]
csv.field_size_limit(1000000)

def arithmetic(op,a,b):
 if op=='+':return a+b
 if op=='-':return a-b
 if op=='*':return a*b
 if op=='/' and a%b==0:return a//b
 raise ValueError('invalid op')
def trace(p,program):
 starts=json.loads(p['starting_values']);targets=set(json.loads(p['targets']));limit=int(p['value_limit']);regs=starts+[None]*(int(p['registers'])-len(starts));seen=targets.intersection(starts);rows=[]
 for i,(op,a,b,d) in enumerate(program,1):
  av,bv=regs[a],regs[b]
  if av is None or bv is None:raise ValueError('undefined operand')
  v=arithmetic(op,av,bv)
  if not 0<v<=limit:raise ValueError('value limit')
  rows.append({'step':i,'op':op,'left':av,'right':bv,'value':v,'target':v in targets});regs[d]=v
  if v in targets:seen.add(v)
 if seen!=targets:raise ValueError('missing target')
 return rows

def factor(n):
 f={int(k):int(v) for k,v in sympy.factorint(n).items()}
 if math.prod(p**e for p,e in f.items())!=n or not all(sympy.isprime(p) for p in f):raise ValueError(f'factorization not complete for {n}')
 return f

def analyze(p,program):
 starts=json.loads(p['starting_values']);targets=json.loads(p['targets']);tr=trace(p,program)
 sf=[factor(x) for x in starts];primes=set().union(*[set(f) for f in sf]);tf=[factor(x) for x in targets]
 full=[{'target':t,'factors':f,'absent_primes':sorted(set(f)-primes),'all_prime_types_in_starts':set(f)<=primes} for t,f in zip(targets,tf)]
 gcds=Counter(math.gcd(a,b) for a,b in itertools.combinations(targets,2));groups=[]
 for g in gcds:
  if g<=1:continue
  members=[t for t in targets if t%g==0]
  if len(members)<2:continue
  examples=[row for row in tr if row['value']==g or (row['op']=='*' and g in (row['left'],row['right']))]
  groups.append({'factor':g,'targets':members,'quotients':[t//g for t in members],'baseline_uses':examples[:8]})
 groups.sort(key=lambda x:(-len(x['targets']),-x['factor']))
 return {'id':p['id'],'starts':[{'value':x,'factors':f} for x,f in zip(starts,sf)],'initial_prime_types':sorted(primes),'limit':int(p['value_limit']),'baseline_steps':len(program),'target_count':len(targets),'all_prime_types_in_starts_count':sum(t['all_prime_types_in_starts'] for t in full),'targets':full,'shared_gcd_groups':groups[:12],'baseline_trace':tr}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--ids',nargs='+',default=['scored_0810','scored_0006','scored_0001']);ap.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');ap.add_argument('--out',type=Path,default=ROOT/'experiments/factor_research_results.json');a=ap.parse_args()
 with (ROOT/'data/puzzles.csv').open(newline='') as f:puzzles={r['id']:r for r in csv.DictReader(f)}
 with a.baseline.open(newline='') as f:programs={r['id']:json.loads(r['program']) for r in csv.DictReader(f) if r['id'] in a.ids}
 cases=[]
 for ident in a.ids:
  print('factoring',ident,flush=True);cases.append(analyze(puzzles[ident],programs[ident]));print('done',ident,flush=True)
 report={'puzzles_sha256':hashlib.sha256((ROOT/'data/puzzles.csv').read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(a.baseline.read_bytes()).hexdigest(),'sympy_version':sympy.__version__,'cases':cases}
 a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
 for c in cases:
  print(c['id'],'steps',c['baseline_steps'],'starts',c['starts'],'targets',c['target_count'],'all start prime types',c['all_prime_types_in_starts_count'])
  for x in c['targets'][:5]:print('target',x)
  for x in c['shared_gcd_groups'][:3]:print('group',x)
if __name__=='__main__':main()
