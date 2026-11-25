// Exact membership in one more arithmetic layer without materializing that layer.
// Input: limit, dictionary size, first anchor index, anchor budget, query count; dictionary; (value, deep) queries.
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <unordered_set>
#include <vector>
#include <sys/resource.h>

using Value = uint64_t;
struct Rule { char op; Value a,b,v; };

class Dictionary {
public:
    Value limit;
    std::vector<Value> priority, sorted;
    std::unordered_set<Value> known;
    uint64_t scans=0, queries=0;

    bool one(Value t, Rule& result, bool defer_slow=false) {
        ++queries;
        if (!t || t>limit) return false;
        if (known.count(t)) {result={'=',t,t,t};return true;}
        const Value m=sorted.back();
        // t = a+b; use the smaller operand, with b <= m.
        auto lower=[&](Value x){return std::lower_bound(sorted.begin(),sorted.end(),x);};
        Value first=t>m?t-m:1;
        if(defer_slow) first=std::max(first,t/21+1);
        for(auto i=lower(first);i!=sorted.end() && *i<=t/2;++i){
            ++scans;
            if(known.count(t-*i)){result={'+',*i,t-*i,t};return true;}
        }
        // t = a-b; search b, never a negative result.
        for(Value b:sorted){
            if(t>=m || b>m-t)break;
            ++scans;
            if(known.count(b+t)){result={'-',b+t,b,t};return true;}
        }
        // t = a*b; b <= m, a <= sqrt(t). Division below avoids overflow.
        for(auto i=lower((t-1)/m+1);i!=sorted.end() && *i<=t/ *i;++i){
            ++scans;
            if(t%*i==0 && known.count(t/ *i)){result={'*',*i,t/ *i,t};return true;}
        }
        // t = a/b; a must be present, so b <= m/t.
        for(Value b:sorted){
            if(b>m/t)break;
            ++scans;
            if(known.count(t*b)){result={'/',t*b,b,t};return true;}
        }
        return false;
    }

    // For t = large+small with gain <= 5%, 21*small <= t.
    // Probe the shorter of the two complementary intervals, without generating siblings.
    bool resume_slow_sum(Value t, Rule& result) {
        if (t<21 || t>limit) return false;
        Value cap=t/21;
        auto small_end=std::upper_bound(sorted.begin(),sorted.end(),cap);
        auto large_begin=std::lower_bound(sorted.begin(),sorted.end(),t-cap);
        auto large_end=std::lower_bound(large_begin,sorted.end(),t);
        auto begin=sorted.begin(), end=small_end;
        if (large_end-large_begin < end-begin) {begin=large_begin; end=large_end;}
        for(auto i=begin;i!=end;++i) {
            ++scans;
            if(known.count(t-*i)){result={'+',*i,t-*i,t};return true;}
        }
        return false;
    }

    std::vector<Rule> probe(Value t, size_t begin, size_t budget, bool deep) {
        Rule inner;
        if(one(t,inner))return {inner};
        if(!deep)return {};
        for(size_t i=begin;i<std::min(budget,priority.size());++i){
            Value a=priority[i];
            auto join=[&](Value x, char op, bool reverse) -> std::vector<Rule> {
                if(!x || x==t || x>limit || !one(x,inner))return {};
                Rule outer={op,reverse?x:a,reverse?a:x,t};
                return {inner,outer};
            };
            std::vector<Rule> rules;
            if(t>a && !(rules=join(t-a,'+',false)).empty())return rules;
            if(t<=limit-a && !(rules=join(t+a,'-',true)).empty())return rules;
            if(a>t && !(rules=join(a-t,'-',false)).empty())return rules;
            if(t%a==0 && !(rules=join(t/a,'*',false)).empty())return rules;
            if(t<=limit/a && !(rules=join(t*a,'/',true)).empty())return rules;
            if(a%t==0 && !(rules=join(a/t,'/',false)).empty())return rules;
        }
        return {};
    }
};
int main(int argc, char** argv){
    bool deferred=argc==2 && std::string(argv[1])=="--defer-slow";
    if(argc!=1 && !deferred) return 2;
    Dictionary d;
    size_t n,begin,budget,count;
    if(!(std::cin>>d.limit>>n>>begin>>budget>>count) || !n)return 2;
    for(size_t i=0;i<n;++i){
        Value x;
        if(!(std::cin>>x) || x==0 || x>d.limit)return 2;
        d.priority.push_back(x);
        d.known.insert(x);
    }
    d.sorted=d.priority;
    std::sort(d.sorted.begin(),d.sorted.end());
    for(size_t j=0;j<count;++j){
        Value t;int deep;
        std::cin>>t>>deep;
        if(deferred){
            Rule hit{};
            std::string status;
            if(d.one(t,hit,true)) status=(hit.op=='=' ? "pinned" : "active");
            else if(d.resume_slow_sum(t,hit)) status="resumed";
            else status="miss";
            std::cout<<t<<" "<<status;
            if(status!="miss")std::cout<<" "<<hit.op<<" "<<hit.a<<" "<<hit.b;
            std::cout<<'\n';
            continue;
        }
        auto rules=d.probe(t,begin,budget,deep);
        std::cout<<t<<" "<<rules.size();
        for(auto r:rules)std::cout<<" "<<r.op<<" "<<r.a<<" "<<r.b<<" "<<r.v;
        std::cout<<'\n';
    }
    struct rusage usage{};
    getrusage(RUSAGE_SELF,&usage);
#if defined(__APPLE__)
    const uint64_t peak=usage.ru_maxrss;
#else
    const uint64_t peak=static_cast<uint64_t>(usage.ru_maxrss)*1024;
#endif
    std::cerr<<d.queries<<" "<<d.scans<<" "<<peak<<"\n";
}
