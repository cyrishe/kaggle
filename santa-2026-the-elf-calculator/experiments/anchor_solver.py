#!/usr/bin/env python3
"""Bounded candidate search with retained target anchors and legal integer halving."""
import json,math
from first_solver import validate

def solve(p,base=16,extended=False,lookahead=False):
 starts=json.loads(p['starting_values']); targets=json.loads(p['targets']); limit=int(p['value_limit']); N=int(p['registers']); m=len(starts)
 if base>limit or m+base+3>=N: raise ValueError('insufficient capacity')
 ops=[];unit=m; ops.append(['/',0,0,unit]); regs={1:unit}
 for n in range(2,base+1):
  regs[n]=m+n-1
  if n%2==0: ops.append(['+',regs[n//2],regs[n//2],regs[n]])
  else: ops.append(['+',regs[n-1],unit,regs[n]])
 acc=m+base; tmp=acc+1; result=acc+2; slots=list(range(result+1,N)); retained=[]
 anchors=[(v,i) for i,v in enumerate(starts)]+[(v,regs[v]) for v in range(1,base+1)]
 def encode(n,dest):
  if n<1 or n>limit: raise ValueError('invalid literal')
  if n in regs:return [['*',regs[n],unit,dest]]
  ds=[]
  while n:n,d=divmod(n,base);ds.append(d)
  ds.reverse(); curr=regs[ds[0]];o=[]
  for d in ds[1:]:
   o.append(['*',curr,regs[base],dest]);curr=dest
   if d:o.append(['+',dest,regs[d],dest])
  return o
 def build_num(n,dest):
  options=[encode(n,dest)]; k=math.isqrt(n)
  for q in (k,k+1):
   sq=q*q
   if q<1 or sq>limit:continue
   diff=abs(n-sq);op=encode(q,dest)+[['*',dest,dest,dest]]
   if diff:
    if dest==tmp:continue
    op+=encode(diff,tmp)+[['+' if sq<n else '-',dest,tmp,dest]]
   options.append(op)
  return min(options,key=len)
 covered=set(starts)|set(range(1,base+1))
 for target_index,t in enumerate(targets):
  if t in covered:continue
  candidates=[build_num(t,acc)]
  available=anchors+retained
  byval={v:r for v,r in available}
  corrections={}
  def correction(d):
   if extended and d in byval:return [],byval[d]
   if extended:
    if d in corrections:return corrections[d]
    for a,ra in available:
     if d>a and d-a in byval:
      result0=([['+',ra,byval[d-a],tmp]],tmp);corrections[d]=result0;return result0
     if a>d and a-d in byval:
      result0=([['-',ra,byval[a-d],tmp]],tmp);corrections[d]=result0;return result0
     if a>0 and d%a==0 and d//a in byval:
      result0=([['*',ra,byval[d//a],tmp]],tmp);corrections[d]=result0;return result0
     if d*a in byval:
      result0=([['/',byval[d*a],ra,tmp]],tmp);corrections[d]=result0;return result0
    result0=(build_num(d,tmp),tmp);corrections[d]=result0;return result0
   return build_num(d,tmp),tmp
  for a,reg in available:
   if a==t: continue
   # Existing anchor, optionally adjusted by a small literal of any size.
   diff=abs(t-a)
   if diff:
    extra,r=correction(diff);path=extra+[['+' if t>a else '-',reg,r,result]]
    candidates.append(path)
   # Explore A², A³, A⁴ and A⁸ as bounded anchors.
   power=a*a
   if a>1 and power<=limit:
    paths=[(power,[['*',reg,reg,acc]])]
    if power*a<=limit: paths.append((power*a,[['*',reg,reg,acc],['*',acc,reg,acc]]))
    p4=power*power
    if p4<=limit:
     p4ops=[['*',reg,reg,acc],['*',acc,acc,acc]];paths.append((p4,p4ops))
     if p4*p4<=limit:paths.append((p4*p4,p4ops+[['*',acc,acc,acc]]))
    for val,steps in paths:
     d=abs(t-val)
     if d==0: candidates.append(steps)
     elif d<=limit:
      extra,r=correction(d);candidates.append(steps+extra+[['+' if val<t else '-',acc,r,result]])
   # Nearby products from cached small multipliers, including powers of two.
   for k in range(2,base+1):
    prod=a*k
    if prod>limit:break
    d=abs(t-prod)
    if d==0: candidates.append([['*',reg,regs[k],result]])
    elif d<t and d<=limit:
     extra,r=correction(d);path=[['*',reg,regs[k],acc]]+extra+[['+' if prod<t else '-',acc,r,result]]
     candidates.append(path)
   # A/2, or (A +/- 1)/2. Exact division only.
   if a%2==0 and a//2==t:candidates.append([['/',reg,regs[2],result]])
   if a%2 and a>1 and (a-1)//2==t:candidates.append([['-',reg,unit,acc],['/',acc,regs[2],result]])
   if a%2 and a+1<=limit and (a+1)//2==t:candidates.append([['+',reg,unit,acc],['/',acc,regs[2],result]])
  if extended:
   # Combine two currently retained larger values; retain only close products.
   large=[(v,r) for v,r in available if v>base]
   for i,(a,ra) in enumerate(large):
    for b,rb in large[i:]:
     product=a*b
     if product>limit:continue
     delta=abs(t-product)
     if delta==0:candidates.append([['*',ra,rb,result]])
     elif delta*20<=t:
      extra,rd=correction(delta)
      candidates.append([['*',ra,rb,acc]]+extra+[['+' if product<t else '-',acc,rd,result]])
  chosen=min(candidates,key=len)
  if slots: dest=slots.pop(0)
  elif retained:
   if lookahead:
    future=targets[target_index+1:]
    def future_distance(item):
     value,_=item
     if not future:return float('inf')
     return min(abs(y-value*k)/y for y in future for k in range(1,base+1) if value*k<=limit)
    victim=max(range(len(retained)),key=lambda i:future_distance(retained[i]))
    _,dest=retained.pop(victim)
   else: _,dest=retained.pop(0)
  else:dest=result
  chosen[-1]=chosen[-1][:3]+[dest]
  ops.extend(chosen); retained.append((t,dest));covered.add(t)
 validate(p,ops)
 return ops
