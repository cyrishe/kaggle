// Single-goal straight-line programs with at most four instructions.
// Process all queries against the same starts-only prefixes. Queries cannot exchange results.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <vector>

using Value = std::uint64_t;
struct Rule {
    char op;
    Value a, b, out;
    bool operator==(const Rule& r) const {
        return op == r.op && a == r.a && b == r.b && out == r.out;
    }
};
using Path = std::vector<Rule>;

struct Search {
    Value limit;
    std::vector<Value> starts, goals;
    std::map<Value, std::vector<Path>> best;

    std::map<Value, Rule> successors(const std::vector<Value>& available) const {
        std::map<Value, Rule> result;
        auto add = [&](char op, Value a, Value b, Value v) {
            if (std::find(available.begin(), available.end(), v) == available.end())
                result.emplace(v, Rule{op, a, b, v});
        };
        for (size_t i = 0; i < available.size(); ++i) {
            for (size_t j = i; j < available.size(); ++j) {
                Value a = std::min(available[i], available[j]);
                Value b = std::max(available[i], available[j]);
                if (a <= limit - b) add('+', a, b, a+b);
                if (a < b) add('-', b, a, b-a);
                if (a <= limit / b) add('*', a, b, a*b);
                if (b % a == 0) add('/', b, a, b/a);
            }
        }
        return result;
    }

    void record(Value goal, Path path) {
        std::set<Value> needed{goal};
        Path used;
        for (auto i = path.rbegin(); i != path.rend(); ++i) {
            if (needed.erase(i->out)) {
                used.push_back(*i);
                needed.insert(i->a);
                needed.insert(i->b);
            }
        }
        std::reverse(used.begin(), used.end());
        auto& found = best[goal];
        if (!found.empty() && used.size() < found.front().size()) found.clear();
        if ((found.empty() || used.size() == found.front().size()) && found.size() < 4 &&
            std::find(found.begin(), found.end(), used) == found.end()) found.push_back(used);
    }

    void visit(std::vector<Value>& available, Path& prefix) {
        auto born = successors(available);
        for (Value t : goals) {
            const auto direct = born.find(t);
            if (direct != born.end()) {
                prefix.push_back(direct->second);
                record(t, prefix);
                prefix.pop_back();
            }
            // All programs of length <=4 are a prefix of at most two operations
            // followed by at most two more. A final operation must use the new
            // value once or twice, or it was already tested by the direct lookup.
            auto join = [&](Value h, char op, Value a, Value b) {
                auto it = born.find(h);
                if (it == born.end() || h == t) return;
                prefix.push_back(it->second);
                prefix.push_back({op, a, b, t});
                record(t, prefix);
                prefix.pop_back();
                prefix.pop_back();
            };
            for (Value c : available) {
                if (t > c) join(t-c,'+',c,t-c);
                if (t <= limit-c) join(t+c,'-',t+c,c);
                if (c > t) join(c-t,'-',c,c-t);
                if (t % c == 0) join(t/c,'*',c,t/c);
                if (t <= limit/c) join(t*c,'/',t*c,c);
                if (c % t == 0) join(c/t,'/',c,c/t);
            }
            if (t % 2 == 0) join(t/2,'+',t/2,t/2);
            Value r = static_cast<Value>(std::sqrt(static_cast<long double>(t)));
            while (r > t/r) --r;
            while (r+1 <= t/(r+1)) ++r;
            if (r*r == t) join(r,'*',r,r);
        }
        if (prefix.size() == 2) return;
        for (const auto& item : born) {
            available.push_back(item.first);
            prefix.push_back(item.second);
            visit(available, prefix);
            prefix.pop_back();
            available.pop_back();
        }
    }
};

int main() {
    Search s;
    size_t ns, ng;
    if (!(std::cin >> s.limit >> ns >> ng) || !ns) return 1;
    s.starts.resize(ns); s.goals.resize(ng);
    for (auto& v : s.starts) std::cin >> v;
    for (auto& t : s.goals) std::cin >> t;
    for (auto t : s.goals)
        if (std::find(s.starts.begin(), s.starts.end(), t) != s.starts.end()) s.record(t,{});
    Path prefix;
    s.visit(s.starts,prefix);
    for (auto t : s.goals) {
        auto& paths = s.best[t];
        std::cout << t << ' ' << paths.size() << '\n';
        for (const auto& path : paths) {
            std::cout << path.size() << '\n';
            for (auto r : path) std::cout << r.op << ' ' << r.a << ' ' << r.b << ' ' << r.out << '\n';
        }
    }
}
