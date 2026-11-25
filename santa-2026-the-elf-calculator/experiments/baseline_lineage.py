"""Build a complete versioned register-lineage database, or trace one value/step."""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path

from depth_graph_study import dag, shallow
from export_50_baseline_cases import DEFAULT_PUZZLES, ROOT


DB = ROOT / 'reports/baseline_lineage.sqlite'
SCHEMA = """
CREATE TABLE puzzles(id TEXT PRIMARY KEY, value_limit INTEGER, registers INTEGER, targets TEXT,
                     steps INTEGER, max_depth INTEGER, f1_count INTEGER, f2_count INTEGER);
CREATE TABLE nodes(puzzle TEXT, step INTEGER, value INTEGER, depth INTEGER, dest INTEGER,
                   op TEXT, left_step INTEGER, right_step INTEGER, target INTEGER,
                   slow_growth INTEGER, direct_users INTEGER, downstream_first_targets INTEGER,
                   PRIMARY KEY(puzzle,step)) WITHOUT ROWID;
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
"""


def build(submission, destination):
    with DEFAULT_PUZZLES.open() as f:
        puzzles={r['id']:r for r in csv.DictReader(f)}
    seen=set()
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        staged=Path(folder)/'lineage.sqlite'
        con=sqlite3.connect(staged)
        try:
            con.executescript(SCHEMA)
            for key,path in [('submission',submission),('puzzles',DEFAULT_PUZZLES)]:
                con.execute('INSERT INTO metadata VALUES (?,?)',(key+'_sha256',hashlib.sha256(path.read_bytes()).hexdigest()))
            with submission.open(newline='') as f, con:
                for row in csv.DictReader(f):
                    ident=row['id']
                    if ident in seen:raise ValueError(f'duplicate {ident}')
                    seen.add(ident)
                    p=puzzles[ident]
                    program=json.loads(row['program'])
                    nodes=dag(p,program)
                    starts=json.loads(p['starting_values'])
                    goals=json.loads(p['targets'])
                    bits={v:1<<i for i,v in enumerate(goals)}
                    by_step={n['step']:n for n in nodes}
                    users=defaultdict(set)
                    downstream=defaultdict(int)
                    for n in reversed(nodes):
                        s=n['step']
                        if n.get('first') or s<0:
                            downstream[s] |= bits.get(n['value'],0)
                        for parent in set(n.get('operands',())):
                            users[parent].add(s)
                            downstream[parent] |= downstream[s]
                    _,counts=shallow(starts,int(p['value_limit']),2)
                    con.execute('INSERT INTO puzzles VALUES (?,?,?,?,?,?,?,?)',
                                (ident,int(p['value_limit']),int(p['registers']),p['targets'],len(program),
                                 max(n['depth'] for n in nodes),counts[1],counts[2]))
                    for n in nodes:
                        s=n['step']
                        a,b=n.get('operands',(None,None))
                        slow=False
                        if a is not None:
                            largest=max(by_step[a]['value'],by_step[b]['value'])
                            slow=largest<n['value'] and 100*n['value']<=105*largest
                        con.execute('INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                    (ident,s,n['value'],n['depth'],n['register'],n.get('op'),a,b,
                                     n['value'] in bits,slow,len(users[s]),bin(downstream[s]).count('1')))
                    # Read the stored producer IDs back and reconstruct the original program exactly.
                    decoded=con.execute("""SELECT n.op,l.dest,r.dest,n.dest FROM nodes n
                        JOIN nodes l ON l.puzzle=n.puzzle AND l.step=n.left_step
                        JOIN nodes r ON r.puzzle=n.puzzle AND r.step=n.right_step
                        WHERE n.puzzle=? ORDER BY n.step""",(ident,))
                    if [list(op) for op in decoded]!=program:
                        raise ValueError(f'round trip failed for {ident}')
            if seen!=puzzles.keys():raise ValueError('coverage mismatch')
            con.executescript("""CREATE INDEX by_value ON nodes(puzzle,value);
                              CREATE INDEX by_left ON nodes(puzzle,left_step);
                              CREATE INDEX by_right ON nodes(puzzle,right_step);""")
            assert con.execute('PRAGMA integrity_check').fetchone()==('ok',)
        finally:
            con.close()
        os.replace(staged,destination)


def trace(db,ident,value=None,step=None):
    with sqlite3.connect(f'{db.resolve().as_uri()}?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        nodes={r['step']:dict(r) for r in con.execute('SELECT * FROM nodes WHERE puzzle=?',(ident,))}
    selected=[r for r in nodes.values() if (r['step']==step if step is not None else r['value']==value)]
    if not selected:raise ValueError('No matching occurrence')
    children=defaultdict(set)
    for s,r in nodes.items():
        for parent in {r['left_step'],r['right_step']}-{None}:
            children[parent].add(s)
    for root in selected:
        ancestors=set()
        stack=[root['step']]
        while stack:
            s=stack.pop()
            if s in ancestors:continue
            ancestors.add(s)
            stack.extend(x for x in (nodes[s]['left_step'],nodes[s]['right_step']) if x is not None)
        print('Value',root['value'],'step',root['step'],'depth',root['depth'],
              'parents',(root['left_step'],root['right_step']),
              'direct consumers',sorted(children[root['step']]))
        for s in sorted(ancestors):
            n=nodes[s]
            rule=('initial' if n['op'] is None else
                  f"{nodes[n['left_step']]['value']} {n['op']} {nodes[n['right_step']]['value']}")
            print(f"{s:4}  depth {n['depth']:2}  r{n['dest']} = {n['value']}  ({rule})")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DB)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('build').add_argument('submission',type=Path)
    cmd=sub.add_parser('trace')
    cmd.add_argument('id')
    group=cmd.add_mutually_exclusive_group(required=True)
    group.add_argument('--value',type=int)
    group.add_argument('--step',type=int)
    args=parser.parse_args()
    if args.action=='build':
        build(args.submission,args.db)
    else:
        trace(args.db,args.id,args.value,args.step)
