// Certify a subset of F5 without materializing F4 or F5. All values <= 1e18.
#include <algorithm>
#include <cstdint>
#include <functional>
#include <iostream>
#include <queue>
#include <vector>
using I = int64_t;
using std::vector;
struct Interval { I lo, hi; };
struct Head { I value, factor; size_t index; bool operator>(const Head& b) const {return value>b.value;} };

int main(){
    I limit; size_t n;
    while(std::cin>>limit>>n){
        vector<I> f(n);
        for(auto& a:f)std::cin>>a;
        if(f.empty() || !std::is_sorted(f.begin(),f.end()) || limit>1000000000000000000LL)return 2;
        vector<Interval> runs;
        for(I a:f){
            if(runs.empty() || a>runs.back().hi+1)runs.push_back({a,a});
            else runs.back().hi=a;
        }
        std::sort(runs.begin(),runs.end(),[](Interval a,Interval b){
            I x=a.hi-a.lo,y=b.hi-b.lo;return x==y?a.lo<b.lo:x>y;
        });
        const I cap=std::min<I>(limit,2000000);
        vector<int> delta(cap+2);
        auto mark=[&](I lo,I hi){
            lo=std::max<I>(1,lo);hi=std::min(cap,hi);
            if(lo<=hi){++delta[lo];--delta[hi+1];}
        };
        for(I a:f)mark(a,a);
        for(size_t i=0;i<std::min<size_t>(12,runs.size());++i){
            const auto block=runs[i];
            for(I a:f){
                mark(a+block.lo,a+block.hi);
                mark(a-block.hi,a-block.lo);
                mark(block.lo-a,block.hi-a);
            }
        }
        // Nearby operands also certify small differences when F3 has few long runs.
        vector<unsigned char> singles(cap+1);
        for(size_t i=0;i<n;++i){
            const size_t stop=std::min(n,i+193);
            for(size_t j=i+1;j<stop;++j){
                I diff=f[j]-f[i];
                if(diff>cap)break;
                singles[diff]=1;
                if(f[j]+f[i]<=cap)singles[f[j]+f[i]]=1;
            }
        }
        I radius=0;int active=0;
        for(I i=1;i<=cap;++i){
            active+=delta[i];
            if(!active && !singles[i])break;
            radius=i;
        }
        // Centers a*b are F4. Both signs of a small F4 residual are legal at F5.
        vector<I> factors={1};
        const size_t pivots=std::min<size_t>(96,f.size());
        if(pivots>1){
            for(size_t i=0;i<pivots;++i)factors.push_back(f[i*(f.size()-1)/(pivots-1)]);
        }
        std::sort(factors.begin(),factors.end());
        factors.erase(std::unique(factors.begin(),factors.end()),factors.end());
        std::priority_queue<Head,vector<Head>,std::greater<Head>> q;
        for(I b:factors)if(f[0]<=limit/b)q.push({f[0]*b,b,0});
        I count=radius, end=radius;
        while(!q.empty() && end<limit){
            Head h=q.top();q.pop();
            I lo=std::max<I>(1,h.value-radius),hi=std::min(limit,h.value+radius);
            if(hi>end){count+=hi-std::max(end,lo-1);end=hi;}
            if(++h.index<f.size() && f[h.index]<=limit/h.factor){
                h.value=f[h.index]*h.factor;q.push(h);
            }
        }
        std::cout<<radius<<" "<<count<<"\n";
    }
}
