#!/usr/bin/env python3
"""Test replacing the public 0810 derivation of 265 with a factor-based one."""
import argparse,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=ROOT/'external/hansen_repository');ap.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');a=ap.parse_args()
 sys.path.insert(0,str(a.repo.resolve()))
 from elf import read_puzzles,read_submission,check
 from graph import active_graph,first_recipes,compile_graph
 p=next(p for p in read_puzzles(ROOT/'data/puzzles.csv') if p.id=='scored_0810');original=read_submission(a.baseline)[p.id];graph=active_graph(p,first_recipes(p,original));candidate=graph.copy()
 candidate.update({20:('+',10,10),260:('*',13,20),5:('/',20,4),265:('+',260,5)})
 draft=active_graph(p,candidate);program=compile_graph(p,draft,attempts=8,recompute=True)
 if program is None:raise RuntimeError('could not allocate candidate to 48 registers')
 check(p,original);check(p,program)
 sys.path.insert(0,str(ROOT/'experiments'))
 from first_solver import validate
 with (ROOT/'data/puzzles.csv').open(newline='') as f:row=next(r for r in csv.DictReader(f) if r['id']==p.id)
 validate(row,program)
 print(json.dumps({'old_steps':len(original),'new_steps':len(program),'old_graph_nodes':len(graph),'new_graph_nodes':len(draft),'added':sorted(set(draft)-set(graph)),'removed':sorted(set(graph)-set(draft))},indent=2))
if __name__=='__main__':main()
