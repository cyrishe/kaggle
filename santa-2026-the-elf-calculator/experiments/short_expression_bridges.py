"""Retrieve small arithmetic DAGs for a requested value without expanding additional global layers."""
from collections import Counter
from itertools import combinations,combinations_with_replacement
from math import gcd
from depth_graph_study import rules


def augment(starts,goals,limit,values,paths,extra_limit=1500):
    levels=[sorted(starts),[],[],[]]
    book={v:None for v in starts}
    cost={v:0 for v in starts}
    def insert(a,b,k):
        x,y=sorted((a,b))
        for op,l,r,v in rules(x,y,limit):
            if 0<v<=limit and v not in book:
                book[v]=(op,l,r,v)
                cost[v]=k
                levels[k].append(v)
    for k in range(1,4):
        for d in range((k-1)//2+1):
            e=k-1-d
            if e==d:
                for a,b in combinations_with_replacement(levels[d],2):insert(a,b,k)
            else:
                for a in levels[d]:
                    for b in levels[e]:insert(a,b,k)
        if k>1:
            for a in levels[k-1]:
                insert(a,a,k)
    freq=Counter(v for seq in paths for v in {x for _,a,b,_ in seq for x in (a,b)})
    queries=list(goals)+[v for v,_ in freq.most_common(160) if v not in starts]
    for a,b in combinations(sorted(goals),2):
        queries.extend([b-a,gcd(a,b)])
        if b%a==0:queries.append(b//a)
    shifts=list(dict.fromkeys(sorted(starts)+[1,2,4]))
    for t in goals:
        for c in shifts:queries.extend([t+c,t-c])
    known=set(values)
    ordered=[v for row in levels for v in sorted(row)]
    maximum=max(ordered)
    cache={}
    def parents(v):
        if v not in cache:
            rule=book[v]
            cache[v]=frozenset([v]) if rule is None else parents(rule[1])|parents(rule[2])|{v}
        return cache[v]
    for t in dict.fromkeys(queries):
        if not 0<t<=limit:continue
        if len(known)-len(values)>=extra_limit:break
        if t in book:known.update(parents(t))
        if t>max(maximum**2,2*maximum):continue
        candidates=[]
        # Output identifies its other positive operand once the first is chosen.
        for a in ordered:
            for b in (t-a,a-t,t+a):
                if b!=t and a!=t and b in book:
                    candidates.append((a,b))
            if t%a==0:
                b=t//a
                if b!=t and a!=t and b in book:candidates.append((a,b))
            if a!=t and a>t and a%t==0 and a//t in book:
                candidates.append((a,a//t))
            if t*a in book and a!=t and t*a!=t:candidates.append((a,t*a))
        # Keep complete derivations, with preference for already shared subexpressions.
        distinct=set(tuple(sorted(x)) for x in candidates)
        ranked=sorted(distinct,key=lambda ab:(len(parents(ab[0])|parents(ab[1])),
                         -freq[ab[0]]-freq[ab[1]],ab))
        for a,b in ranked[:12]:
            known.update(parents(a));known.update(parents(b));known.add(t)
    return sorted(known),len(book)
