import csv,json,math,statistics
from pathlib import Path
rows=[]
for kind,filename in [('scored','data/puzzles.csv'),('practice','data/practice_puzzles.csv')]:
 with open(filename,newline='') as f:
  for p in csv.DictReader(f):
   ts=json.loads(p['targets']); lo=min(ts);hi=max(ts);limit=int(p['value_limit'])
   lowroot=math.isqrt(lo-1);uproot=math.isqrt(hi)+1
   low=lowroot**2;up=uproot**2
   rows.append(dict(dataset=kind,id=p['id'],family=p.get('family',''),count=len(ts),min_target=lo,max_target=hi,value_limit=limit,lower_root=lowroot,lower_square=low,lower_valid=int(low>0),lower_diff_min=lo-low,lower_diff_max=hi-low,lower_max_diff_ratio=(hi-low)/hi,lower_reduction=low/hi,upper_root=uproot,upper_square=up,upper_valid=int(up<=limit),upper_diff_min=up-hi,upper_diff_max=up-lo,upper_max_diff_ratio=(up-lo)/hi,upper_reduction=1-(up-lo)/hi))
with open('experiments/square_anchor_analysis.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
for kind in ['scored','practice']:
 rr=[x for x in rows if x['dataset']==kind]; print(kind,'n',len(rr),'upper legal',sum(x['upper_valid'] for x in rr),'lower valid',sum(x['lower_valid'] for x in rr))
 for name,eligible in [('lower_reduction',[x for x in rr if x['lower_valid']]),('upper_reduction',[x for x in rr if x['upper_valid']])]:
  vals=[x[name] for x in eligible]; print(name,'median',statistics.median(vals),'positive',sum(v>0 for v in vals),'atleast50%',sum(v>=.5 for v in vals))
 print('scored_0001',next((x for x in rr if x['id']=='scored_0001'),''))
