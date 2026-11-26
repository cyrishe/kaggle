// Multi-output signed quotient walks. Values and operands are kept unsigned and
// positive.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using V = std::uint64_t;
struct Rule {
  V a = 0, b = 0;
  char op = ' ';
  int cost = 0;
};
using Book = std::unordered_map<V, Rule>;
struct Plan {
  V n;
  double paid;
  std::vector<std::pair<V, Rule>> tail;
};
struct Alternative {
  double rank;
  V q;
  V f;
  V r;
  bool up;
};
struct Solver {
  V limit;
  int slots, mode, width;
  std::vector<V> starts, targets;
  std::mt19937_64 rng;
  Book shallow, live, one;
  std::vector<V> factors, residents, seeds;
  std::vector<std::tuple<char, int, int, int>> program;
  std::unordered_set<V> hit;
  std::unordered_map<V, int> popularity, reuse;
  std::uniform_real_distribution<double> uniform{0., 1.};
  double rnd() { return uniform(rng); }
  template <class F> void operations(V a, V b, F add) {
    if (a > b)
      std::swap(a, b);
    if (a <= limit - b)
      add(a + b, Rule{a, b, '+'});
    if (b > a)
      add(b - a, Rule{b, a, '-'});
    if (a <= limit / b)
      add(a * b, Rule{a, b, '*'});
    if (b % a == 0)
      add(b / a, Rule{b, a, '/'});
  }
  void prepare() {
    for (auto s : starts)
      shallow[s] = {};
    for (int level = 1; level <= 3; level++) {
      Book next = shallow;
      std::vector<std::pair<V, Rule>> last(shallow.begin(), shallow.end());
      for (size_t i = 0; i < last.size(); i++)
        for (size_t j = 0; j <= i; j++) {
          V a = last[i].first, b = last[j].first;
          auto ra = last[i].second, rb = last[j].second;
          int cost = 1 + ra.cost + (a == b ? 0 : rb.cost);
          operations(a, b, [&](V v, Rule r) {
            if (v == a || v == b ||
                (level == 3 && (mode < 1 || (v > 160000 && cost > 3))))
              return;
            r.cost = cost;
            auto it = next.find(v);
            if (it == next.end() || cost < it->second.cost)
              next[v] = r;
          });
        }
      shallow.swap(next);
      if (level == 2 && mode == 0)
        break;
    }
    for (auto &[v, r] : shallow)
      if (v >= 2 && v <= 100000000 && r.cost <= 3)
        seeds.push_back(v);
    std::sort(seeds.begin(), seeds.end());
    // Score shared exact and shifted divisors over different targets (once per
    // target).
    for (auto f : seeds) {
      int count = 0;
      for (auto t : targets) {
        if (t % f == 0) {
          count += 3;
          continue;
        }
        bool matches = false;
        for (auto s : starts)
          if (t % f == s % f || (t % f && f - t % f == s % f)) {
            matches = true;
            break;
          }
        count += matches;
      }
      popularity[f] = count;
    }
  }
  int cost(V v) const {
    if (!v || live.count(v))
      return 0;
    if (one.count(v))
      return 1;
    auto it = shallow.find(v);
    return it == shallow.end() ? 1000 : it->second.cost;
  }
  int shared_support(V value) const {
    auto found = popularity.find(value);
    return found == popularity.end() ? 0 : found->second;
  }

  void snapshot() {
    residents.clear();
    one.clear();
    factors.clear();
    for (auto &[v, r] : live)
      residents.push_back(v);
    std::sort(residents.begin(), residents.end());
    for (size_t i = 0; i < residents.size(); i++)
      for (size_t j = 0; j <= i; j++)
        operations(residents[i], residents[j], [&](V v, Rule r) {
          if (!live.count(v)) {
            r.cost = 1;
            one.emplace(v, r);
          }
        });
    for (auto v : residents)
      if (v > 1 && v <= 1000000000000ULL)
        factors.push_back(v);
    std::vector<std::pair<double, V>> choices;
    auto consider = [&](V v, int c) {
      if (v < 2 || v > 1000000000000ULL || live.count(v))
        return;
      double bonus = mode >= 2 ? 0.6 * std::log2(1 + shared_support(v)) : 0.;
      double score = 0.24 * std::min(18., std::log2(double(v))) - c * 1.45 +
                     bonus + 1.0 * rnd();
      choices.emplace_back(-score, v);
    };
    for (auto &[v, r] : one)
      consider(v, 1);
    for (auto v : seeds)
      if (!one.count(v))
        consider(v, shallow.at(v).cost);
    std::sort(choices.begin(), choices.end());
    for (int i = 0; i < std::min(210, (int)choices.size()); i++)
      factors.push_back(choices[i].second);
    for (V v : {2, 4, 8, 16, 32})
      if (cost(v) < 100)
        factors.push_back(v);
    std::sort(factors.begin(), factors.end());
    factors.erase(std::unique(factors.begin(), factors.end()), factors.end());
  }
  // Exact fallback; positive binary recurrence decreases strictly to one.
  void materialize(V n, std::unordered_set<V> &known,
                   std::vector<std::pair<V, Rule>> &out) {
    if (known.count(n))
      return;
    Rule r;
    if (one.count(n))
      r = one.at(n);
    else if (shallow.count(n))
      r = shallow.at(n);
    else if (n % 2 == 0)
      r = Rule{n / 2, n / 2, '+'};
    else
      r = Rule{n - 1, 1, '+'};
    if (!r.a)
      throw std::runtime_error("missing start");
    materialize(r.a, known, out);
    materialize(r.b, known, out);
    known.insert(n);
    out.emplace_back(n, r);
  }
  std::vector<std::pair<V, Rule>> expand(const Plan &s, Rule final) {
    std::unordered_set<V> known(residents.begin(), residents.end());
    std::vector<std::pair<V, Rule>> out;
    auto add = [&](V v, Rule r) {
      if (known.count(v))
        return;
      materialize(r.a, known, out);
      materialize(r.b, known, out);
      out.emplace_back(v, r);
      known.insert(v);
    };
    if (final.a)
      add(s.n, final);
    else
      materialize(s.n, known, out);
    for (auto it = s.tail.rbegin(); it != s.tail.rend(); ++it)
      add(it->first, it->second);
    return out;
  }
  std::vector<std::pair<V, Rule>> search(V target) {
    Plan root{target, 0, {}};
    auto best = expand(root, {});
    std::vector<Plan> beam{root};
    for (int d = 0; d <= 7 && !beam.empty(); d++) {
      std::vector<std::pair<double, Plan>> next;
      for (auto &s : beam) {
        auto check = [&](Rule r) {
          auto p = expand(s, r);
          if (p.size() < best.size())
            best.swap(p);
        };
        auto n = s.n;
        int nc = cost(n);
        if (nc < 1000 || n < 300)
          check({});
        // Price inverse matches exactly where the unfinished quotient meets
        // an operand already constructed and one shallow/one-step operand.
        for (auto a : residents) {
          auto attempt = [&](V v, Rule r) {
            if (v && v <= limit && s.paid + cost(v) + 1 <= best.size() + 1)
              check(r);
          };
          if (n > a)
            attempt(n - a, Rule{a, n - a, '+'});
          if (a > n)
            attempt(a - n, Rule{a, a - n, '-'});
          if (a <= limit - n)
            attempt(n + a, Rule{n + a, a, '-'});
          if (a > 1 && n % a == 0)
            attempt(n / a, Rule{a, n / a, '*'});
        }
        if (n < 3 || d == 7 || s.paid + 1 >= best.size())
          continue;
        std::vector<Alternative> candidates;
        auto offer = [&](V f, V q, V r, bool up) {
          if (!q || q >= n || q > limit / f || q * f == r || q == 1)
            return;
          int fc = cost(f), rc = cost(r);
          if (rc > 8)
            return;
          double paid = s.paid + 1 + bool(r) + fc + rc;
          if (paid >= best.size() + 1)
            return;
          double terminal = cost(q);
          if (terminal > 99)
            terminal = 1.7 + 0.34 * std::log2(double(q));
          double bonus = mode >= 2 ? 0.20 * std::log2(1 + shared_support(f)) : 0.;
          double rank = paid + terminal - bonus + 0.65 * rnd();
          candidates.push_back({rank, q, f, r, up});
        };
        for (auto f : factors)
          if (f <= n) {
            V q = n / f, r = n % f;
            offer(f, q, r, false);
            if (r)
              offer(f, q + 1, f - r, true);
            // Non-nearest corrections are admitted if a large live value is
            // congruent.
            if (mode >= 2 && (live.count(f) || shared_support(f) >= 3) && f > 64) {
              for (auto a : residents)
                if (a >= f) {
                  if (n > a && (n - a) % f == 0)
                    offer(f, (n - a) / f, a, false);
                  if (a <= limit - n && (n + a) % f == 0)
                    offer(f, (n + a) / f, a, true);
                }
            }
          }
        size_t k = std::min<size_t>(width, candidates.size());
        std::partial_sort(candidates.begin(), candidates.begin() + k,
                          candidates.end(),
                          [](auto &a, auto &b) { return a.rank < b.rank; });
        for (size_t i = 0; i < k; i++) {
          auto [rank, q, f, r, up] = candidates[i];
          Plan p = s;
          p.n = q;
          p.paid += 1 + bool(r) + cost(f) + cost(r);
          if (r)
            p.tail.emplace_back(n, Rule{f * q, r, up ? '-' : '+'});
          p.tail.emplace_back(f * q, Rule{f, q, '*'});
          next.emplace_back(rank, std::move(p));
        }
      }
      std::sort(next.begin(), next.end(),
                [](auto &a, auto &b) { return a.first < b.first; });
      beam.clear();
      std::unordered_set<V> seen;
      for (auto &p : next)
        if (seen.insert(p.second.n).second) {
          beam.push_back(std::move(p.second));
          if ((int)beam.size() >= width)
            break;
        }
    }
    return best;
  }
  void emit(const std::vector<std::pair<V, Rule>> &path) {
    std::unordered_map<V, int> needs;
    for (auto &[v, r] : path) {
      needs[r.a]++;
      needs[r.b]++;
    }
    for (auto &[v, r] : path) {
      --needs[r.a];
      --needs[r.b];
      if (live.count(v))
        continue;
      int a = live.at(r.a).cost, b = live.at(r.b).cost, dest = 0;
      if ((int)live.size() < slots) {
        std::vector<bool> taken(slots, false);
        for (auto &[u, row] : live)
          taken[row.cost] = true;
        dest = std::find(taken.begin(), taken.end(), false) - taken.begin();
      } else {
        double worst = 1e99;
        V evict = 0;
        for (auto &[u, row] : live)
          if (!needs[u] &&
              std::find(starts.begin(), starts.end(), u) == starts.end()) {
            double score = std::log2(1. + reuse[u]) * 2 +
                           0.30 * std::log2(1. + shared_support(u)) +
                           (u <= 2048 ? 1. : 0.) + 1.2 * rnd();
            if (score < worst) {
              evict = u;
              worst = score;
            }
          }
        if (!evict)
          throw std::runtime_error("register pressure");
        dest = live.at(evict).cost;
        live.erase(evict);
      }
      program.emplace_back(r.op, a, b, dest);
      live[v] = Rule{0, 0, ' ', dest};
      ++reuse[r.a];
      ++reuse[r.b];
      hit.insert(v);
    }
  }
  void run() {
    live.clear();
    one.clear();
    reuse.clear();
    hit.clear();
    program.clear();
    for (size_t i = 0; i < starts.size(); i++) {
      live[starts[i]] = Rule{0, 0, ' ', (int)i};
      hit.insert(starts[i]);
    }
    auto order = targets;
    for (size_t i = 0; i < order.size(); i += 5)
      std::shuffle(order.begin() + i,
                   order.begin() + std::min(i + 5, order.size()), rng);
    for (auto t : order)
      if (!hit.count(t)) {
        snapshot();
        emit(search(t));
      }
  }
};
int main() {
  Solver s;
  int count, nt, trials;
  unsigned seed;
  if (!(std::cin >> s.limit >> s.slots >> count >> nt >> s.mode >> s.width >>
        trials >> seed))
    return 1;
  s.starts.resize(count);
  s.targets.resize(nt);
  for (auto &x : s.starts)
    std::cin >> x;
  for (auto &x : s.targets)
    std::cin >> x;
  s.rng.seed(seed);
  s.prepare();
  for (int i = 0; i < trials; i++) {
    s.rng.seed(seed + i * 4409U);
    s.run();
    std::cout << i << " " << s.program.size() << "\n";
    for (auto [o, a, b, d] : s.program)
      std::cout << o << " " << a << " " << b << " " << d << "\n";
    std::cout.flush();
  }
}
