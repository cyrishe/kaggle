"""Find short single-target programs by joining two small arithmetic expressions.

The catalogue keeps one recipe per numeric value. The search uses +, -, *.
The caller supplies the live values and schedules the returned operations.
"""
from itertools import combinations_with_replacement


def catalogue(values, limit, depth):
    recipes = dict.fromkeys(values)
    layers = [list(recipes)]
    for cost in range(1, depth + 1):
        layer = []
        for left_cost in range((cost - 1) // 2 + 1):
            right_cost = cost - 1 - left_cost
            left, right = layers[left_cost], layers[right_cost]
            pairs = (combinations_with_replacement(left, 2) if left_cost == right_cost
                     else ((a, b) for a in left for b in right))
            for a, b in pairs:
                hi, lo = max(a, b), min(a, b)
                for value, op in ((hi + lo, '+'), (hi - lo, '-'), (hi * lo, '*')):
                    if 0 < value <= limit and value not in recipes:
                        recipes[value] = (op, hi, lo)
                        layer.append(value)
        layers.append(layer)
    return recipes


def find_program(target, values, limit, depth=3):
    recipes = catalogue(values, limit, depth)

    def expand(root, last):
        built = set(values)
        steps = []
        def build(v, rule):
            if v in built:
                return
            op, a, b = rule
            build(a, recipes[a])
            build(b, recipes[b])
            steps.append((op, a, b, v))
            built.add(v)
        build(root, last)
        return steps

    best = expand(target, recipes[target]) if target in recipes else None
    for a in recipes:
        matches = [('+', a, target - a), ('-', a, a - target), ('-', a + target, a)]
        if target % a == 0:
            matches.append(('*', a, target // a))
        for op, x, y in matches:
            if x == target or y == target or x not in recipes or y not in recipes:
                continue
            steps = expand(target, (op, x, y))
            if best is None or len(steps) < len(best):
                best = steps
    return best
