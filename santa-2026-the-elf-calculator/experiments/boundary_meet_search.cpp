// Search a prefix using its mandatory outputs and a bounded number of novel values.
// Input: limit, number of starts, initial values, number of prefix results,
// then (value, required) pairs. All start and result values must be distinct.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <set>
#include <vector>

using Value = int64_t;
struct Op { char symbol; Value a, b, value; };
using Steps = std::vector<Op>;

Value limit_value;
std::vector<Value> starts, original, mandatory, optional_values;
std::vector<Value> allowed;
Steps solution;
int max_helpers_to_unlock;
uint64_t calls = 0, subsets = 0;

bool contains(const std::vector<Value>& s, Value v) {
    return std::binary_search(s.begin(), s.end(), v);
}
void insert(std::vector<Value>& s, Value v) {
    s.insert(std::lower_bound(s.begin(), s.end(), v), v);
}

// Solve x op known = target (both operand orders), then check if x is available.
bool finish(Value t, const std::vector<Value>& s, Op& op) {
    for (Value a : s) {
        auto test = [&](Value b, char sign, bool reverse) {
            if (b <= 0 || !contains(s,b)) return false;
            op = {sign, reverse ? b : a, reverse ? a : b, t};
            return true;
        };
        if (test(t-a,'+',false) || test(t+a,'-',true) || test(a-t,'-',false)
            || (t%a==0 && test(t/a,'*',false))
            || (a%t==0 && test(a/t,'/',false))
            || (t<=limit_value/a && test(t*a,'/',true))) return true;
    }
    return false;
}
bool close(std::vector<Value>& s, Steps& path) {
    bool changed;
    do {
        changed=false;
        for (Value t : allowed) {
            Op op;
            if (!contains(s,t) && finish(t,s,op)) {
                insert(s,t);
                path.push_back(op);
                changed=true;
            }
        }
    } while (changed);
    return std::all_of(mandatory.begin(),mandatory.end(),[&](Value t){return contains(s,t);});
}
bool solve(std::vector<Value> s, Steps path, int left, int streak=0) {
    ++calls;
    size_t before_close=s.size();
    if (close(s,path)) {solution=path;return true;}
    if (left==0) return false;
    if (s.size()>before_close) streak=0;
    bool require_bridge = left==1 || streak+1>=max_helpers_to_unlock;
    // When only one novel value is left it must unlock an allowed result.
    // Invert the last operation from each blocked result to form a meet table.
    std::vector<Value> backward;
    if (require_bridge) {
        for (Value t : allowed) if (!contains(s,t)) {
            for (Value a : s) {
                backward.push_back(t-a); backward.push_back(t+a); backward.push_back(a-t);
                if (t%a==0) backward.push_back(t/a);
                if (a%t==0) backward.push_back(a/t);
                if (t<=limit_value/a) backward.push_back(t*a);
            }
            if (t%2==0) backward.push_back(t/2);
            Value root=static_cast<Value>(std::sqrt(static_cast<double>(t)));
            if (root*root==t) backward.push_back(root);
        }
        std::sort(backward.begin(),backward.end());
    }
    std::set<Value> tried;
    auto try_op = [&](char sign,Value a,Value b,Value v) {
        if (v<=0 || v>limit_value || (require_bridge && !contains(backward,v))
            || contains(original,v) || contains(s,v) || !tried.insert(v).second) return false;
        auto next=s; insert(next,v);
        path.push_back({sign,a,b,v});
        bool ok=solve(next,path,left-1,streak+1);
        path.pop_back();
        return ok;
    };
    for (size_t i=0;i<s.size();++i) for (size_t j=0;j<=i;++j) {
        Value a=s[i], b=s[j];
        if (try_op('+',a,b,a+b) || try_op('-',a,b,a-b)
            || (a<=limit_value/b && try_op('*',a,b,a*b))
            || (a%b==0 && try_op('/',a,b,a/b))) return true;
    }
    return false;
}
bool choose(size_t pos,int omit,int novel,std::vector<Value>& kept) {
    if (omit<0 || static_cast<size_t>(omit)>optional_values.size()-pos) return false;
    if (pos==optional_values.size()) {
        allowed=mandatory;
        allowed.insert(allowed.end(),kept.begin(),kept.end());
        ++subsets;
        return solve(starts,{},novel);
    }
    if (choose(pos+1,omit-1,novel,kept)) return true;
    kept.push_back(optional_values[pos]);
    bool found=choose(pos+1,omit,novel,kept);
    kept.pop_back();
    return found;
}
int main(int argc,char** argv) {
    if (argc!=3 && argc!=4) return 2;
    max_helpers_to_unlock=argc==4 ? std::stoi(argv[3]) : 100;
    int novel=std::stoi(argv[1]), savings=std::stoi(argv[2]), n, m;
    if (!(std::cin>>limit_value>>n) || limit_value>2000000000 || novel<0 || savings<0) return 2;
    starts.resize(n);
    for (Value& v : starts) std::cin>>v;
    std::sort(starts.begin(),starts.end());
    std::cin>>m;
    for (int i=0;i<m;++i) {
        Value v; int required;
        std::cin>>v>>required;
        original.push_back(v);
        (required ? mandatory : optional_values).push_back(v);
    }
    std::sort(original.begin(),original.end());
    std::vector<Value> kept;
    bool ok=choose(0,novel+savings,novel,kept);
    std::cout<<(ok?"FOUND":"NONE")<<" "<<subsets<<" "<<calls<<"\n";
    if (ok) for (auto op : solution) std::cout<<op.symbol<<" "<<op.a<<" "<<op.b<<" "<<op.value<<"\n";
}
