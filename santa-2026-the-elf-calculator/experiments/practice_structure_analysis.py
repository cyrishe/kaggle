import csv,json,math,statistics,collections
out=[]
with open('data/practice_puzzles.csv',newline='') as f:
 for r in csv.DictReader(f):
  t=json.loads(r['targets']);s=json.loads(r['starting_values']); limit=int(r['value_limit']);n=len(t)
  pairs=[(a,b) for i,a in enumerate(t) for b in t[i+1:]]
  close=lambda a,b,threshold: (b-a)*threshold<=b
  near1=sum(close(a,b,100) for a,b in pairs);near4=sum(close(a,b,10000) for a,b in pairs)
  groups=[];g=[t[0]]
  for a,b in zip(t,t[1:]):
   if close(a,b,10000):g.append(b)
   else:groups.append(g);g=[b]
  groups.append(g);clusters=[x for x in groups if len(x)>=2]
  links=[]
  for a,b in pairs:
   best=None
   for k in s:
    if k<=1 or a*k>limit:continue
    error=abs(a*k-b); rec=(error/b,error,a,k,b)
    if best is None or rec<best:best=rec
   if best is not None:links.append(best)
  near_mul1=sum(x[0]<=.01 for x in links);near_mul4=sum(x[0]<=.0001 for x in links)
  nearest=[min(abs(x-y)/max(x,y) for y in t if y!=x) for x in t] if n>1 else []
  roots=collections.Counter(math.isqrt(x) for x in t)
  out.append(dict(id=r['id'],family=r['family'],tier=r['design_tier'],n=n,max_digits=len(str(max(t))),min_digits=len(str(min(t))),start_count=len(s),near1=near1,near4=near4,pairs=len(pairs),clusters=len(clusters),cluster_targets=sum(map(len,clusters)),largest_cluster=max(map(len,clusters),default=0),root_groups=sum(v>=2 for v in roots.values()),root_max=max(roots.values()),mul1=near_mul1,mul4=near_mul4,nearest_median=statistics.median(nearest) if nearest else '',best_mul=json.dumps(min(links) if links else None),example_cluster=json.dumps(max(clusters,key=len) if clusters else [])))
with open('experiments/practice_structure_features.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=out[0].keys());w.writeheader();w.writerows(out)
for family in sorted({x['family'] for x in out}):
 R=[x for x in out if x['family']==family]; p=sum(x['pairs'] for x in R)
 print('\n',family,'n',len(R),'maxdigits median',statistics.median(x['max_digits'] for x in R),'range',min(x['max_digits'] for x in R),max(x['max_digits'] for x in R),'median nearest%',statistics.median([x['nearest_median'] for x in R if x['nearest_median']!=''])*100)
 print('near pairs 1%,0.01%',sum(x['near1'] for x in R),sum(x['near4'] for x in R),'of',p,'clusters >=2 puzzles',sum(x['clusters']>=2 for x in R),'clustered targets',sum(x['cluster_targets'] for x in R),'of',sum(x['n'] for x in R),'rootgroups>=2',sum(x['root_groups']>=2 for x in R))
 print('mul pairs 1%,0.01%',sum(x['mul1'] for x in R),sum(x['mul4'] for x in R),'puzzles any',sum(x['mul1']>0 for x in R),sum(x['mul4']>0 for x in R))
 print('example best cluster', max(R,key=lambda x:x['clusters'])['id'],max(x['clusters'] for x in R));print('bestmul',min((x for x in R if x['mul4']>0),key=lambda x:json.loads(x['best_mul'])[0],default={}).get('id'))
