"""Check restart state, historical coverage and the inclusive instruction cap."""
import unittest
from capped_path_walk import Checkpoint, Trace
from hybrid_graph_search import Construction, live_rollout
from first_solver import validate


class WalkTests(unittest.TestCase):
    def test_cap_is_inclusive(self):
        p = dict(id='tiny', starting_values='[2]', targets='[4]', value_limit=10, registers=48)
        for cap, expected in [(1,True),(0,False)]:
            program,stats = live_rollout(Construction(p),virtual=True,walk=Trace(cap))
            self.assertEqual(program is not None,expected)
            if expected:
                self.assertEqual(validate(p,program)[0],1)
            else:
                self.assertEqual(stats['cutoff'],1)

    def test_resume_after_overwrite(self):
        p = dict(id='tiny', starting_values='[2]',targets='[4,8,16]',value_limit=20,registers=48)
        old = Checkpoint((('+',0,0,1),('+',1,1,1)),((2,0),(8,1)),frozenset({4,8}))
        program,_ = live_rollout(Construction(p),virtual=True,walk=Trace(3,[old]))
        self.assertEqual(validate(p,program)[0],3)


if __name__=='__main__':
    unittest.main()
