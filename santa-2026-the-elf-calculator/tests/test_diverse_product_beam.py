"""Regression: preserve paths that are useful to later targets."""
import csv,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(puzzle,base,out,width):
 subprocess.run([sys.executable,str(ROOT/'experiments/diverse_product_beam.py'),'--puzzles',str(puzzle),'--baseline',str(base),'--ids','toy','--out',str(out),'--width',str(width),'--slack',str(0 if width==1 else 2)],check=True)
 return json.loads((out/'report.json').read_text())['rows'][0]
def write(tmp,starts,targets,program):
 puzzle=tmp/'puzzles.csv';base=tmp/'base.csv'
 with puzzle.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['id','starting_values','targets','value_limit','registers']);w.writerow(['toy',json.dumps(starts),json.dumps(targets),500,48])
 with base.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['id','program']);w.writerow(['toy',json.dumps(program)])
 return puzzle,base
def main():
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp)
  puzzle,base=write(tmp,[2,3,5],[11,22,30],[['+',2,1,3],['+',3,1,4],['+',4,4,5],['*',1,2,6],['+',6,6,7]])
  result=run(puzzle,base,tmp/'first',5);assert result['before']==5 and result['after']==4,result
  puzzle,base=write(tmp,[2,3,5],[18,44,180],[['*',2,1,3],['+',3,1,4],['+',2,1,5],['+',4,3,6],['+',6,4,7],['-',7,3,8],['*',8,2,9],['+',8,5,10]])
  greedy=run(puzzle,base,tmp/'greedy',1);diverse=run(puzzle,base,tmp/'diverse',5)
  assert greedy['after']==8 and diverse['after']==6,(greedy,diverse)
 print('product search: both synthetic regressions passed')
if __name__=='__main__':main()
