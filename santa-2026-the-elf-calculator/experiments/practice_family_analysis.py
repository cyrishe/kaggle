import csv,json,math,statistics,collections
rows=list(csv.DictReader(open('data/practice_puzzles.csv',newline='')))
results=[]
for r in rows:
 t=json.loads(r['targets']);s=json.loads(r['starting_values']); paired=len(t)*(len(t)-1)//2
 near=sum((b-a)*10000<=b for i,a in enumerate(t) for b in t[i+1:])
 sq=collections.Counter(math.isqrt(x) for x in t)
 shared=sum(n*(n-1)//2 for n in sq.values())
 divis=sum(any(v%x==0 for x in s) for v in t)
 edges=set()
 for a in t:
  for b in s:
   for z in [a+b,a-b,a*b]+([a//b] if a%b==0 else []):
    if z in t and z!=a:edges.add(tuple(sorted((a,z))))
 results.append(dict(id=r['id'],family=r['family'],tier=r['design_tier'],targets=len(t),starts=len(s),maxdigits=len(str(max(t))),min_digits=len(str(min(t))),pairs=paired,near_pairs=near,shared_root_pairs=shared,divisible=divis,one_step_links=len(edges)))
for fam in sorted(set(x['family'] for x in results)):
 r=[x for x in results if x['family']==fam]; n=len(r); pairs=sum(x['pairs'] for x in r); targets=sum(x['targets'] for x in r)
 print(fam,'n',n,'tiers',dict(collections.Counter(x['tier'] for x in r)),'median_targets',statistics.median(x['targets'] for x in r),'median_max_digits',statistics.median(x['maxdigits'] for x in r),'target_count',targets,'pair_count',pairs,'near',sum(x['near_pairs'] for x in r),'sqrtshare',sum(x['shared_root_pairs'] for x in r),'sqrt_puzzles',sum(x['shared_root_pairs']>0 for x in r),'divisible',sum(x['divisible'] for x in r),'onestep_puzzles',sum(x['one_step_links']>0 for x in r),'onestep_edges',sum(x['one_step_links'] for x in r))
 x=max(r,key=lambda x:x['one_step_links']);print('most links example',x['id'],x['one_step_links'])
with open('experiments/practice_family_features.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=results[0].keys());w.writeheader();w.writerows(results)
