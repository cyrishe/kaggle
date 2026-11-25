import json
import unittest
from first_solver import validate
from hybrid_graph_search import Construction, graph_search, live_rollout, local_repair, shared_helper_repair


class HybridGraphTest(unittest.TestCase):
    def test_remove_shared_helper_and_replay_both_consumers(self):
        p = dict(id='shared', starting_values='[2,3,7,12,28]', targets='[15,35]',
                 registers=48, value_limit=35)
        initial = [['+',0,1,5], ['*',5,1,6], ['*',5,2,7]]
        program, edits = shared_helper_repair(p,initial,11)
        self.assertEqual(validate(p,program)[0], 2)
        self.assertEqual(edits[0]['old'], 5)

    def test_shared_factors_and_short_value_limits(self):
        for starts, goals, limit in [
            ([1], [1], 1), ([7], [1, 2, 3, 7], 7),
            ([7, 11, 13], [143, 286, 429, 431], 431),
            ([11, 31, 57], [15324, 18388, 20931, 20934], 21500)
        ]:
            with self.subTest(starts=starts):
                p = dict(id='test', starting_values=json.dumps(starts), targets=json.dumps(goals),
                         registers=48, value_limit=limit)
                model = Construction(p)
                initial = model.construct()
                graph, _ = graph_search(model, initial)
                randomized, _ = graph_search(model, graph, random_seed=23)
                self.assertLessEqual(len(randomized), len(initial))
                for virtual in (False, True):
                    for seed in (None, 23):
                        program, _ = live_rollout(model, seed, virtual)
                        validate(p, program)
                        fixed, _ = local_repair(p, program, 23, budget=5, reschedule=True)
                        validate(p, fixed)
                        self.assertLessEqual(len(fixed), len(program))


if __name__ == '__main__':
    unittest.main()
