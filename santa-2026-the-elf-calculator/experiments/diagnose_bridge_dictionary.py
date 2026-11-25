"""Oracle experiment on missing numerical values. Do not use these programs as independent results."""
import csv
import json
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from benchmark_joint_bridges import DEFAULT_PUZZLES, ROOT, run

if __name__=='__main__':
    ids=['scored_0253','scored_0035','scored_0667']
    with DEFAULT_PUZZLES.open() as file:puzzles={p['id']:p for p in csv.DictReader(file)}
    out={}
    with tempfile.TemporaryDirectory() as folder:
        binary=Path(folder)/'diagnose'
        subprocess.run(['c++','-O3','-std=c++17',str(Path(__file__).with_name('joint_bridge_search.cpp')),'-o',str(binary)],check=True)
        with ProcessPoolExecutor(max_workers=3) as pool:
            jobs=[(puzzles[i],binary,500,20261125,[],False,False,mode)
                  for i in ids for mode in ('all_values','matched_noise')]
            for i,r in pool.map(run,jobs):
                out.setdefault(i,{})[r['diagnostic'][0]]=r
    (ROOT/'reports/diagnostic_public_value_intervention.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
