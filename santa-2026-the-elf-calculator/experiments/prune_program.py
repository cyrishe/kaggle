"""Remove instructions that do not contribute to the first coverage of a target."""
import json
from first_solver import validate

def prune(p,program):
 starts=json.loads(p['starting_values']);targets=set(json.loads(p['targets']));values=starts+[None]*(int(p['registers'])-len(starts));versions=[None]*len(values);roots=[];covered=set(starts)&targets;deps=[]
 for idx,(op,i,j,d) in enumerate(program):
  a,b=values[i],values[j]
  if op=='+': v=a+b
  elif op=='-': v=a-b
  elif op=='*': v=a*b
  elif op=='/':
   if not b or a%b:raise ValueError('invalid division')
   v=a//b
  else:raise ValueError('invalid op')
  deps.append((versions[i],versions[j]));values[d]=v;versions[d]=idx
  if v in targets and v not in covered:covered.add(v);roots.append(idx)
 if covered!=targets:raise ValueError('incomplete')
 required=set();stack=roots[:]
 while stack:
  n=stack.pop()
  if n is None or n in required:continue
  required.add(n);stack.extend(deps[n])
 result=[op for idx,op in enumerate(program) if idx in required]
 validate(p,result)
 return result
