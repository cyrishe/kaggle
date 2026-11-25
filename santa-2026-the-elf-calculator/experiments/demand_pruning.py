"""Resume selected correction branches only for specific target/product gaps."""
from bisect import bisect_left
from depth_graph_study import inverse


def targeted_plan(target, pending, live, partners, one_step, costs, limit,
                  leaf, merge, search, baseline, stats, joint):
    """Return a validated-by-construction single or two-target arithmetic plan."""
    if len(baseline)<=1:
        return baseline
    products = {}
    for a in sorted(live - {1}):
        i = bisect_left(partners, (target+a-1)//a)
        for b in partners[max(0,i-2):i+2]:
            p = a*b
            if p<=limit and b>1 and p not in products:
                products[p] = (a,b)
    def priority(p):
        d = abs(target-p)
        return (int(d!=0 and d not in live and d not in costs),
                int(p not in live) + int(products[p][1] not in live),
                d)
    ranked = sorted(products,key=priority)
    # Reserve half of the probes for the nearest products even when the
    # correction is absent from the cache. The missing value triggers a lookup.
    shortlist = list(dict.fromkeys(ranked[:8] + sorted(products,key=lambda p:abs(target-p))[:8]))
    stats['product_candidates'] += len(products)
    stats['product_probes'] += len(shortlist)
    leaves = live | set(one_step)
    memo = {}
    def correction(d):
        if d in memo:
            return memo[d]
        best = leaf(d) if d in live or d in costs else None
        if best is None or len(best)>1:
            stats['inverse_requests'] += 1
            for a in live:
                for op,x,y in inverse(d,a,limit):
                    if d in (x,y) or x not in leaves or y not in leaves:
                        continue
                    trial = merge(leaf(x),leaf(y),[(op,x,y,d)])
                    if best is None or len(trial)<len(best):
                        best = trial
            if best is not None and d not in costs and d not in live:
                stats['resumed_gaps'] += 1
        memo[d] = best
        return best
    def finish(t,p):
        a,b = products[p]
        head = [] if p in live else merge(leaf(b),[('*',a,b,p)])
        if t==p:
            return head
        d = abs(t-p)
        fix = correction(d)
        if fix is None:
            return None
        return merge(head,fix,[('+' if t>p else '-',p,d,t)])
    single = baseline
    proposals = []
    for p in shortlist:
        plan = finish(target,p)
        if plan is None:
            continue
        if len(plan)<len(single):
            single = plan
        if joint and len(plan)<=len(baseline)+1:
            # Give the same product a second customer before growing more branches.
            for other in sorted(pending-{target}, key=lambda t: abs(t-p))[:3]:
                other_plan = finish(other,p)
                if other_plan is not None:
                    proposals.append((other,merge(plan,other_plan)))
    if proposals:
        alternatives = {}
        best_gain = 0
        chosen = None
        for other,plan in proposals:
            if other not in alternatives:
                alternatives[other] = search(other,3)
            gain = len(merge(single, alternatives[other]))-len(plan)
            if gain>best_gain:
                best_gain, chosen = gain, plan
        if chosen is not None:
            stats['paired_plans'] += 1
            return chosen
    stats['shorter_single_plans'] += len(single)<len(baseline)
    return single
