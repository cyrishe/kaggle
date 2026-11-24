#!/usr/bin/env python3
"""Rebuild two targets through a shared offset factor and replay the entire graph."""
import argparse,sys,json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=ROOT/'external/hansen_repository');ap.add_argument('--baseline',type=Path,default=ROOT/'external/asterios_v196/merged_132477.csv');a=ap.parse_args()
 sys.path.insert(0,str(a.repo.resolve()))
 from elf import read_puzzles,read_submission,check
 from graph import active_graph,first_recipes,compile_graph
 p=next(p for p in read_puzzles(ROOT/'data/puzzles.csv') if p.id=='scored_0901');program=read_submission(a.baseline)[p.id];old=active_graph(p,first_recipes(p,program));proposal=old.copy()
 proposal.update({117:('*',9,13),26:('+',13,13),35:('+',26,9),4095:('*',117,35),4104:('+',4095,9),22:('+',13,9),31:('+',22,9),148:('+',117,31),17316:('*',117,148),17307:('-',17316,9)})
 graph=active_graph(p,proposal);candidate=compile_graph(p,graph,attempts=8,recompute=True)
 if candidate is None:raise RuntimeError('no physical allocation')
 check(p,program);check(p,candidate)
 sys.path.insert(0,str(ROOT/'experiments'))
 from first_solver import validate
 with (ROOT/'data/puzzles.csv').open(newline='') as f:row=next(r for r in csv.DictReader(f) if r['id']==p.id)
 validate(row,program);validate(row,candidate)
 print(json.dumps({'id':p.id,'original_instructions':len(program),'candidate_instructions':len(candidate),'original_nodes':len(old),'candidate_nodes':len(graph),'removed':sorted(set(old)-set(graph)),'added':sorted(set(graph)-set(old))},indent=2))
if __name__=='__main__':main()
