// Search arithmetic DAGs over a finite numeric dictionary, with positive integer intermediates.
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using namespace std;
using U = uint64_t;
struct Rule {int a,b,v; char op;};
struct Solution {vector<int> steps; int peak=0;};
struct Search {
    int n, slots, limitSteps;
    vector<U> value;
    vector<int> starts,goals;
    vector<char> initial,goal;
    vector<Rule> edges;
    vector<vector<int>> defs,uses;
    vector<Solution> source;
    unordered_map<U,int> index;
    mt19937 rng;
    explicit Search(unsigned seed):rng(seed){}
    double uniform(){return generate_canonical<double,32>(rng);}
    void add(int a,int b,int v,char op){
        if(initial[v] || a==v || b==v) return;
        int i=edges.size(); edges.push_back({a,b,v,op}); defs[v].push_back(i);
        uses[a].push_back(i); if(b!=a) uses[b].push_back(i);
    }
    void read(){
        int m,t; cin>>n>>m>>t>>slots>>limitSteps;
        value.resize(n); initial.assign(n,0); goal.assign(n,0);
        defs.resize(n);uses.resize(n);
        for(int i=0;i<n;++i){cin>>value[i];index[value[i]]=i;}
        for(int j=0,x;j<m;++j){cin>>x;starts.push_back(x);initial[x]=1;}
        for(int j=0,x;j<t;++j){cin>>x;goals.push_back(x);goal[x]=1;}
        U top=value.back();
        for(int a=0;a<n;++a) for(int b=a;b<n;++b){
            U x=value[a],y=value[b];
            if(x<=top-y){
                auto it=index.find(x+y);
                if(it!=index.end()){
                    int c=it->second; add(a,b,c,'+');add(c,a,b,'-');if(a!=b)add(c,b,a,'-');
                }
            }
            if(x<=top/y){
                auto it=index.find(x*y);
                if(it!=index.end()){
                    int c=it->second; add(a,b,c,'*');add(c,a,b,'/');if(a!=b)add(c,b,a,'/');
                }
            }
        }
        int sources;cin>>sources;
        for(int j=0;j<sources;++j){
            int length;cin>>length;vector<int> recipe(n,-1),order=starts;
            for(int k=0;k<length;++k){
                int a,b,v;char op;cin>>op>>a>>b>>v;
                if(initial[v]||recipe[v]>=0)continue;
                if((op=='+'||op=='*')&&a>b)swap(a,b);
                auto pos=find_if(defs[v].begin(),defs[v].end(),[&](int id){
                    auto e=edges[id];return e.op==op&&e.a==a&&e.b==b;
                });
                if(pos==defs[v].end())throw runtime_error("source recipe missing from dictionary");
                recipe[v]=*pos;order.push_back(v);
            }
            auto seed=extract(recipe,order);
            if(!seed.steps.empty())source.push_back(seed);
        }
    }
    Solution extract(const vector<int>& recipe,const vector<int>& forward){
        vector<int> order;
        vector<char> need=initial;
        function<void(int)> visit=[&](int v){
            if(need[v])return;
            need[v]=1;
            const auto &e=edges[recipe[v]];
            visit(e.a); visit(e.b);order.push_back(recipe[v]);
        };
        for(int v:goals){if(!initial[v] && recipe[v]<0)return {};visit(v);}
        if((int)order.size()>limitSteps)return {};
        auto pressure = [&](const vector<int>& seq){
            vector<int> counts(n);
            for(int i:seq){auto e=edges[i];counts[e.a]++;counts[e.b]++;}
            int live=0,peak=starts.size();
            for(int v:starts)live+=counts[v]>0;
            for(int i:seq){
                auto e=edges[i];
                if(--counts[e.a]==0)--live;
                if(--counts[e.b]==0)--live;
                peak=max(peak,live+1);
                live+=counts[e.v]>0;
            }
            return peak;
        };
        int p=pressure(order);
        if(p>slots){
            order.clear();
            for(int v:forward)if(need[v]&&!initial[v])order.push_back(recipe[v]);
            p=pressure(order);
        }
        return p<=slots?Solution{order,p}:Solution{};
    }
    // Relax the cost of arithmetic trees. Positive prices ensure selected rules are acyclic.
    Solution priced(double noise,const vector<char>* discount=nullptr){
        vector<double> cost(n,1e60),price(n);
        vector<int> recipe(n,-1),forward;
        vector<char> settled(n);
        for(int i=0;i<n;++i)price[i]=exp(noise*(uniform()-0.5))*((discount && (*discount)[i])?0.12:1.0);
        using Item=pair<double,int>;
        priority_queue<Item,vector<Item>,greater<Item>> pq;
        for(int v:starts){cost[v]=0;pq.emplace(0,v);}
        int remaining=goals.size();
        while(!pq.empty()){
            auto [best,v]=pq.top();pq.pop();
            if(settled[v])continue;
            settled[v]=1;forward.push_back(v);
            if(goal[v]&&--remaining==0)break;
            for(int id:uses[v]){
                auto e=edges[id];if(settled[e.v]||!settled[e.a]||!settled[e.b])continue;
                double next=price[e.v]+cost[e.a]+(e.a==e.b?0:cost[e.b]);
                if(next<cost[e.v]){cost[e.v]=next;recipe[e.v]=id;pq.emplace(next,e.v);}
            }
        }
        return extract(recipe,forward);
    }
    Solution grow(){
        // Pay for a numeric helper once. Recompute marginal costs after each
        // block, treating already purchased values as additional zero-cost roots.
        vector<char> ready=initial;
        vector<int> available=starts, paid=starts, chosen(n,-1);
        vector<double> prices(n);
        double jitter=0.3+2.7*uniform();
        for(double& w:prices)w=exp(jitter*(uniform()-0.5));
        int left=0;for(int t:goals)left+=!ready[t];
        using Item=pair<double,int>;
        while(left){
            vector<double> d(n,1e60);vector<int> path(n,-1),hits;
            vector<char> done(n);
            priority_queue<Item,vector<Item>,greater<Item>> q;
            for(int v:available){d[v]=0;q.emplace(0,v);}
            int width=min(left,1+int(rng()%3));
            while(!q.empty() && (int)hits.size()<width){
                auto [cost,v]=q.top();q.pop();
                if(done[v])continue;
                done[v]=1;
                if(goal[v]&&!ready[v])hits.push_back(v);
                for(int id:uses[v]){
                    auto e=edges[id];if(done[e.v]||!done[e.a]||!done[e.b])continue;
                    double c=prices[e.v]+d[e.a]+(e.b==e.a?0:d[e.b]);
                    if(c<d[e.v]){d[e.v]=c;path[e.v]=id;q.emplace(c,e.v);}
                }
            }
            if(hits.empty())return {};
            int t=hits[rng()%hits.size()];
            function<void(int)> buy=[&](int v){
                if(ready[v])return;
                int id=path[v];auto e=edges[id];buy(e.a);buy(e.b);
                ready[v]=1;left-=goal[v];chosen[v]=id;available.push_back(v);paid.push_back(v);
            };
            buy(t);
        }
        return extract(chosen,paid);
    }
    // Return extra values that can replace inputs of several existing numeric recipes.
    vector<int> bridges(const Solution& s,bool guided,int count){
        vector<char> have=initial;
        for(int i:s.steps)have[edges[i].v]=1;
        vector<double> score(n);
        vector<int> stamp(n,-1);
        for(int i:s.steps){
            int v=edges[i].v;
            for(int id:defs[v]){
                auto e=edges[id];
                if(!have[e.a]&&!have[e.b]&&e.a!=e.b)continue;
                int h=!have[e.a]?e.a:e.b;
                if(!have[h]&&stamp[h]!=v){score[h]+=1;stamp[h]=v;}
            }
        }
        vector<pair<double,int>> ranked;
        for(int h=0;h<n;++h)if(score[h]>0){
            bool reachable=false;
            for(int id:defs[h]){
                auto e=edges[id];
                if(have[e.a]&&have[e.b]){reachable=true;break;}
            }
            if(reachable){
                double weight=guided?pow(score[h],2.2):1;
                // Independent exponential clocks sample without replacement.
                ranked.emplace_back(-log(max(uniform(),1e-12))/weight,h);
            }
        }
        int take=min(count,(int)ranked.size());
        partial_sort(ranked.begin(),ranked.begin()+take,ranked.end());
        vector<int> out;for(int j=0;j<take;++j)out.push_back(ranked[j].second);
        return out;
    }
    // Restrict arithmetic to the parent graph plus the proposed helpers. Repeatedly
    // remove a value only if the whole target set remains reachable from the real starts.
    Solution reduce(const Solution& parent,vector<int> extra){
        vector<char> active=initial;
        vector<int> vertices=starts;
        auto enable=[&](int v){if(!active[v]){active[v]=1;vertices.push_back(v);}};
        for(int id:parent.steps)enable(edges[id].v);
        for(int v:extra)enable(v);
        vector<vector<int>> local(n);
        for(int v:vertices)for(int id:defs[v]){
            auto e=edges[id];if(active[e.a]&&active[e.b]){
                local[e.a].push_back(id);if(e.a!=e.b)local[e.b].push_back(id);
            }
        }
        vector<int> mark(n,0),recipe(n,-1),order;
        int pass=0;
        auto closure=[&](){
            ++pass;order=starts;int reached=0;
            for(int v:starts){mark[v]=pass;reached+=goal[v];}
            for(size_t j=0;j<order.size() && reached<(int)goals.size();++j){
                for(int id:local[order[j]]){
                    auto e=edges[id];
                    if(!active[e.v]||mark[e.v]==pass||mark[e.a]!=pass||mark[e.b]!=pass)continue;
                    mark[e.v]=pass;recipe[e.v]=id;order.push_back(e.v);reached+=goal[e.v];
                }
            }
            return reached==(int)goals.size();
        };
        shuffle(vertices.begin(),vertices.end(),rng);
        for(int v:vertices)if(!initial[v]&&!goal[v]){
            active[v]=0;if(!closure())active[v]=1;
        }
        if(!closure())return {};
        return extract(recipe,order);
    }
    void emit(const string& arm,int budget,const Solution& best,double sec,const vector<int>& curve,int distinct){
        cout<<arm<<" "<<budget<<" "<<best.steps.size()<<" "<<best.peak<<" "<<sec<<" "<<distinct;
        for(int x:curve)cout<<" "<<x;
        cout<<"\n";
        for(int i:best.steps){
            auto e=edges[i];cout<<e.op<<" "<<e.a<<" "<<e.b<<" "<<e.v<<"\n";
        }
    }
    void run(int budget,int seed,bool marginal){
        auto baseline=priced(0);
        for(const auto& s:source)if(baseline.steps.empty()||s.steps.size()<baseline.steps.size())baseline=s;
        if(baseline.steps.empty())throw runtime_error("no schedulable deterministic seed");
        emit("tree",1,baseline,0,{},1);
        for(int arm=0;arm<(marginal?4:3);++arm){
            rng.seed(seed);
            auto begin=chrono::steady_clock::now();
            Solution best=baseline; vector<Solution> elite{baseline};
            for(const auto& s:source)if(elite.size()<8)elite.push_back(s);
            vector<int> curve; unordered_set<U> unique;
            for(int i=0;i<budget;++i){
                bool fresh=arm==0||i<12||i%10==0;
                Solution s;
                if(fresh){
                    s=arm==3?grow():priced(0.6+3.5*uniform());
                }else{
                    const Solution& p=elite[rng()%elite.size()];
                    auto extra=bridges(p,arm>=2,i%5==0?32:2+rng()%10);
                    if(i%5==1 || i%5==2){
                        vector<char> discount=initial;
                        for(int id:p.steps)discount[edges[id].v]=(uniform()<0.8);
                        // The new graph can cross more than one missing helper. Its
                        // full ancestry remains eligible for joint deletion.
                        auto donor=arm==3 && i%10==2?grow():priced(1.0+3.0*uniform(),i%5==1?&discount:nullptr);
                        for(int id:donor.steps)extra.push_back(edges[id].v);
                    }else if(elite.size()>1&&i%4==0){
                        const auto& donor=elite[rng()%elite.size()];
                        for(int id:donor.steps)extra.push_back(edges[id].v);
                    }
                    s=reduce(p,extra);
                }
                if(!s.steps.empty()){
                    if(s.steps.size()<best.steps.size())best=s;
                    U hash=0;for(int id:s.steps){U v=U(edges[id].v)+1;v=(v^(v>>16))*0x9e3779b97f4a7c15ULL;hash^=v^(v>>29);}
                    if(unique.insert(hash).second){
                        elite.push_back(s);
                        stable_sort(elite.begin(),elite.end(),[](const auto& a,const auto& b){return a.steps.size()<b.steps.size();});
                        if(elite.size()>8)elite.pop_back();
                    }
                }
                if(i==49||i==249||i+1==budget)curve.push_back(best.steps.size());
            }
            double seconds=chrono::duration<double>(chrono::steady_clock::now()-begin).count();
            emit(arm==0?"random_tree":arm==1?"uniform_bridge":arm==2?"shared_bridge":"shared_growth",budget,best,seconds,curve,unique.size());
        }
    }
};
int main(int argc,char** argv){
    if(argc!=3&&argc!=4)return 1;
    int seed=stoi(argv[2]); Search search(seed);search.read();
    cout<<search.n<<" "<<search.edges.size()<<"\n";
    search.run(stoi(argv[1]),seed,argc==4);
}
