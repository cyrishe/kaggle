"""Compare all sparse query outcomes and witnesses against explicit tiny closures."""
import random
import subprocess
import tempfile
import unittest
from itertools import combinations_with_replacement
from pathlib import Path

from sparse_depth_study import limited_layers, run_queries
from deferred_growth_study import probe


def explicit(values,limit):
    result=set(values)
    for a,b in combinations_with_replacement(sorted(values),2):
        result.update(v for v in (a+b,b-a,a*b) if 0<v<=limit)
        if b%a==0:result.add(b//a)
    return result


class SparseQueriesTest(unittest.TestCase):
    def test_all_four_operations(self):
        rng=random.Random(253)
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'query'
            subprocess.run(['c++','-O2','-std=c++17',str(Path(__file__).with_name('sparse_depth_query.cpp')),'-o',str(binary)],check=True)
            # On this boundary 100 + 5 is slow, 100 + 6 is active.
            self.assertEqual(probe(binary,200,{5,100},[105])[105][0],'resumed')
            self.assertEqual(probe(binary,200,{6,100},[106])[106][0],'active')
            for _ in range(50):
                limit=rng.randint(20,110)
                values=set(rng.sample(range(1,limit+1),rng.randint(1,8)))
                expected=explicit(values,limit)
                deferred=probe(binary,limit,values,range(1,limit+1))
                self.assertEqual({v for v,(status,_) in deferred.items() if status!='miss'},expected)
                double=explicit(expected,limit)
                for deep in (False,True):
                    hits,_=run_queries(binary,limit,sorted(values),[(t,deep) for t in range(1,limit+1)],len(values))
                    if not deep:self.assertEqual(set(hits),expected)
                    else:self.assertTrue(expected<=hits.keys()<=double)
                    for t,path in hits.items():
                        known=set(values)
                        for op,a,b,v in path:
                            self.assertTrue(a in known and b in known)
                            if op=='/':self.assertEqual(a%b,0)
                            self.assertEqual(v,{'=':a,'+':a+b,'-':a-b,'*':a*b,'/':a//b}[op])
                            self.assertTrue(0<v<=limit)
                            known.add(v)
                        self.assertIn(t,known)
                for budget in (8,50,100000):
                    book,counts,_=limited_layers(sorted(values),limit,pair_budget=budget,value_budget=limit)
                    closed=set(values)
                    for _ in counts[1:]:
                        closed=explicit(closed,limit)
                    self.assertEqual(set(book),closed)


if __name__=='__main__':
    unittest.main()
