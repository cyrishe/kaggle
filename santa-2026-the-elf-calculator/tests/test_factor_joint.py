"""Regression: a shared composite factor saves three physical steps."""
import csv,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp);puzzle=tmp/'puzzles.csv';program=tmp/'program.csv';factors=tmp/'factors.json';out=tmp/'out'
  with puzzle.open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['id','starting_values','targets','value_limit','registers']);w.writerow(['toy',json.dumps([2,3,7]),json.dumps([30,70]),100,48])
  with program.open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['id','program']);w.writerow(['toy',json.dumps([['+',0,1,3],['*',3,1,4],['+',4,4,5],['*',2,2,6],['*',2,1,7],['+',6,7,8]])])
  factors.write_text(json.dumps({'cases':[{'id':'toy','targets':[{'target':30,'factors':{'2':1,'3':1,'5':1}},{'target':70,'factors':{'2':1,'5':1,'7':1}}]}]}))
  subprocess.run([sys.executable,str(ROOT/'experiments/factor_joint_pilot.py'),'--puzzles',str(puzzle),'--baseline',str(program),'--factors',str(factors),'--out',str(out)],check=True)
  result=json.loads((out/'report.json').read_text())['rows'][0]
  assert result['before']==6 and result['after']==3 and result['win']['factor']==10,result
 print('shared-factor synthetic regression passed')
if __name__=='__main__':main()
