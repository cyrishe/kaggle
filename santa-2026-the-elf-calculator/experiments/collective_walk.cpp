// Search for a low-cost signed residual or an exact (possibly shifted) quotient
// from values currently present. Search recipes are materialized only on demand.
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using namespace std;
using U = uint64_t;
struct E {
  char op;
  U a, b, v;
};
using Path = vector<E>;
struct V {
  int cost;
  E rule;
};
struct Trail {
  int price;
  U need;
  Path suffix;
  double priority;
};
struct Machine {
  U limit;
  vector<U> reg, goals;
  vector<int> uses, age;
  vector<E> output;
  unordered_set<U> hit;
  mt19937_64 rng;
  int mode;
  Machine(vector<U> starts, vector<U> targets, U lim, int registers, int m, U seed)
      : limit(lim), reg(registers), goals(targets), uses(registers), age(registers), rng(seed),
        mode(m) {
    copy(starts.begin(), starts.end(), reg.begin());
    hit.insert(starts.begin(), starts.end());
  }
  int slot(U v) const { return int(find(reg.begin(), reg.end(), v) - reg.begin()); }
  double noise() { return double(rng() >> 11) * 0x1p-53; }
  void emit(const Path &p) {
    for (int i = 0; i < int(p.size()); ++i) {
      auto e = p[i];
      if (slot(e.v) < int(reg.size()))
        continue;
      int a = slot(e.a), b = slot(e.b);
      if (a == int(reg.size()) || b == int(reg.size()))
        throw runtime_error("missing operand");
      int d = slot(0);
      if (d == int(reg.size())) {
        unordered_set<U> protected_values;
        for (int j = i + 1; j < int(p.size()); ++j) {
          protected_values.insert(p[j].a);
          protected_values.insert(p[j].b);
        }
        double low = 1e9;
        for (int j = 0; j < int(reg.size()); ++j) {
          U x = reg[j];
          if (protected_values.count(x) || x == 1 || x == 2)
            continue;
          // Retain small constants, gap-sized operands and recently productive values.
          double score = 1.4 * min(uses[j], 6) + 3.0 / (1.0 + 0.04 * (output.size() - age[j])) +
                         (x <= 32 ? 3 : 0) + (has_single_bit(x) ? 1.4 : 0) + noise();
          if (mode) {
            for (U t : goals)
              if (!hit.count(t) && t > x && t % x == 0)
                score += 0.5;
          }
          if (score < low) {
            low = score;
            d = j;
          }
        }
      }
      if (d == int(reg.size()))
        throw runtime_error("no free slot");
      ++uses[a];
      ++uses[b];
      age[a] = age[b] = output.size();
      output.push_back({e.op, U(a), U(b), U(d)});
      reg[d] = e.v;
      uses[d] = 0;
      age[d] = output.size();
      hit.insert(e.v);
    }
  }
  void init() {
    U a = reg[0];
    emit({{'/', a, a, 1}});
    if (limit >= 2)
      emit({{'+', 1, 1, 2}});
    for (int k : {2, 4, 8, 16, 32, 3, 6, 12, 24}) {
      if (k >= 63 || (U(1) << k) > limit)
        continue;
      int i = k / 2, j = k - i;
      U x = U(1) << i, y = U(1) << j;
      if (slot(x) < int(reg.size()) && slot(y) < int(reg.size()))
        emit({{'*', x, y, x * y}});
    }
  }
  void seed_odd_ladder() {
    if (limit < 5)
      return;
    emit({{'+', 1, 2, 3}, {'+', 2, 3, 5}});
    vector<U> pivots;
    for (U x : reg)
      if (x >= 3 && !has_single_bit(x))
        pivots.push_back(x);
    shuffle(pivots.begin(), pivots.end(), rng);
    stable_sort(pivots.begin(), pivots.end(), [](U a, U b) { return (a >= 20) > (b >= 20); });
    U a = pivots.front(), b = pivots.size() > 1 ? pivots[1] : 3, x = a;
    for (int j = 0; j < 10; ++j) {
      U y = j % 3 == 0 ? b : a;
      if (x > limit / y)
        break;
      emit({{'*', x, y, x * y}});
      x *= y;
    }
  }
  struct Book {
    Machine &m;
    unordered_map<U, V> recipes;
    vector<vector<U>> levels;
    vector<U> ready, radix, probe;
    struct ModIndex {
      U base;
      unordered_map<U, U> representative;
    };
    vector<ModIndex> moduli;
    Book(Machine &mach) : m(mach), levels(4) {
      recipes.reserve(90000);
      for (U x : m.reg)
        if (x)
          put(x, 0, {0, 0, 0, x});
      ready = levels[0];
      for (size_t i = 0; i < ready.size(); ++i)
        for (size_t j = i; j < ready.size(); ++j)
          combine(ready[i], ready[j], 1);
      if (m.mode) {
        // Sample across logarithmic magnitude, allowing broad coverage at small cost.
        auto first = levels[1];
        shuffle(first.begin(), first.end(), m.rng);
        vector<int> per(65);
        for (U x : first)
          if (per[bit_width(x)]++ < 3)
            for (U y : ready)
              combine(x, y, 2);
        auto second = levels[2];
        shuffle(second.begin(), second.end(), m.rng);
        fill(per.begin(), per.end(), 0);
        for (U x : second)
          if (per[bit_width(x)]++ < 1)
            for (U y : ready)
              combine(x, y, 3);
      }
      for (auto &row : levels)
        sort(row.begin(), row.end());
      radix = ready;
      if (m.mode) {
        vector<int> per(65);
        auto f = levels[1];
        shuffle(f.begin(), f.end(), m.rng);
        for (U x : f)
          if (per[bit_width(x)]++ < 4)
            radix.push_back(x);
      }
      if (m.mode == 3) {
        probe = ready;
        auto layer = levels[1];
        shuffle(layer.begin(), layer.end(), m.rng);
        vector<int> per(65);
        for (U x : layer)
          if (per[bit_width(x)]++ < 3)
            probe.push_back(x);
      }
      if (m.mode >= 2) {
        // A cheap signed adjustment may be many multiples away from a canonical remainder.
        // Keep a low-cost representative in each residue class of sampled live magnitudes.
        auto bases = ready;
        shuffle(bases.begin(), bases.end(), m.rng);
        vector<int> per(65);
        for (U a : bases)
          if (a >= 64 && (!per[bit_width(a)]++ || has_single_bit(a))) {
            ModIndex idx{a, {}};
            idx.representative.reserve(min<U>(a, recipes.size()));
            for (int c = 0; c <= 2; ++c)
              for (U r : levels[c])
                idx.representative.emplace(r % a, r);
            moduli.push_back(std::move(idx));
          }
      }
    }
    void put(U x, int cost, E e) {
      if (recipes.emplace(x, V{cost, e}).second)
        levels[cost].push_back(x);
    }
    void combine(U a, U b, int c) {
      if (a < b)
        swap(a, b);
      if (a <= m.limit - b)
        put(a + b, c, {'+', a, b, a + b});
      if (a > b)
        put(a - b, c, {'-', a, b, a - b});
      if (a <= m.limit / b)
        put(a * b, c, {'*', a, b, a * b});
      if (a % b == 0)
        put(a / b, c, {'/', a, b, a / b});
    }
    void materialize(U x, Path &p) const {
      auto v = recipes.at(x);
      if (!v.cost)
        return;
      materialize(v.rule.a, p);
      if (v.rule.b != v.rule.a)
        materialize(v.rule.b, p);
      p.push_back(v.rule);
    }
    Path clean(Path p) const {
      unordered_set<U> seen(ready.begin(), ready.end());
      Path q;
      for (E e : p)
        if (seen.insert(e.v).second)
          q.push_back(e);
      return q;
    }
    Path solve(U target) {
      Path best;
      // Always-complete fallback. Ensure its only external leaves (1,2) are live.
      vector<char> digits;
      for (U x = target; x > 1; x /= 2)
        digits.push_back(x & 1);
      U x = 1;
      for (auto it = digits.rbegin(); it != digits.rend(); ++it) {
        best.push_back({'+', x, x, x + x});
        x += x;
        if (*it) {
          best.push_back({'+', x, 1, x + 1});
          ++x;
        }
      }
      best = clean(best);
      vector<Trail> fringe{{0, target, {}, 0}};
      unordered_map<U, int> cheapest;
      for (int depth = 0; !fringe.empty() && depth < 7; ++depth) {
        vector<Trail> next;
        for (auto &s : fringe) {
          U n = s.need;
          auto finish = [&](Path p) {
            p.insert(p.end(), s.suffix.begin(), s.suffix.end());
            p = clean(p);
            if (p.size() < best.size())
              best = std::move(p);
          };
          if (recipes.count(n)) {
            Path p;
            materialize(n, p);
            finish(std::move(p));
          }
          // Terminal joins: the left expression can be one new instruction, the
          // right can be up to three levels deep in the sampled forward dictionary.
          auto join = [&](U a, U b, E e) {
            auto it = recipes.find(b);
            if (it == recipes.end())
              return;
            if (s.price + 1 + max(recipes.at(a).cost, it->second.cost) >= int(best.size()))
              return;
            Path p;
            materialize(a, p);
            materialize(b, p);
            p.push_back(e);
            finish(std::move(p));
          };
          for (int c = 0; c <= 1; ++c) {
            if (s.price + c + 1 >= int(best.size()))
              continue;
            for (U a : levels[c]) {
              if (a < n)
                join(a, n - a, {'+', a, n - a, n});
              if (a > n)
                join(a, a - n, {'-', a, a - n, n});
              if (a <= m.limit - n)
                join(a, n + a, {'-', n + a, a, n});
              if (a > 1 && n % a == 0)
                join(a, n / a, {'*', a, n / a, n});
              if (a > 1 && n <= m.limit / a)
                join(a, n * a, {'/', n * a, a, n});
            }
          }
          auto propose = [&](U q, Path connector) {
            if (!q || q >= n)
              return;
            connector.insert(connector.end(), s.suffix.begin(), s.suffix.end());
            connector = clean(connector);
            int price = connector.size();
            if (price >= int(best.size()))
              return;
            if (recipes.count(q)) {
              Path p;
              materialize(q, p);
              p.insert(p.end(), connector.begin(), connector.end());
              p = clean(p);
              if (p.size() < best.size())
                best = std::move(p);
              return;
            }
            auto it = cheapest.find(q);
            if (it != cheapest.end() && it->second <= price)
              return;
            cheapest[q] = price;
            double priority = price + 0.18 * log2(double(q) + 1) + m.noise() * 0.65;
            next.push_back({price, q, std::move(connector), priority});
          };
          for (auto const &layer : levels) {
            if (layer.empty())
              continue;
            auto it = lower_bound(layer.begin(), layer.end(), n);
            int k = int(it - layer.begin());
            for (int j = max(0, k - 3); j < min(int(layer.size()), k + 3); ++j) {
              U a = layer[j];
              if (a == n)
                continue;
              U q = a > n ? a - n : n - a;
              Path p;
              materialize(a, p);
              p.push_back(a > n ? E{'-', a, q, n} : E{'+', a, q, n});
              propose(q, std::move(p));
            }
          }
          if (m.mode == 3 && depth < 3) {
            // Meet a requested number in the middle without storing every product / difference.
            // Search for a very cheap neighbor v=a*b or v=a±b, then request exactly |n-v|.
            struct Nearby {
              double score;
              E combine;
              U residual;
            };
            vector<Nearby> near;
            auto offer = [&](E e, int cost) {
              U q = e.v > n ? e.v - n : n - e.v;
              if (e.v == 0 || q >= n || cost + s.price >= int(best.size()))
                return;
              auto known = recipes.find(q);
              double estimate = q == 0                   ? 0
                                : known != recipes.end() ? 1 + known->second.cost
                                                         : 1 + 0.19 * log2(double(q) + 1);
              near.push_back({estimate + cost, e, q});
            };
            for (U a : probe)
              for (int c = 0; c <= 2; ++c) {
                const auto &pool = levels[c];
                if (pool.empty())
                  continue;
                int cost = 1 + c + recipes.at(a).cost;
                auto inspect = [&](U want, char op) {
                  auto it = lower_bound(pool.begin(), pool.end(), want);
                  auto check = [&](U b) {
                    if (op == '*') {
                      if (a <= m.limit / b)
                        offer({'*', a, b, a * b}, cost);
                    } else if (op == '+') {
                      if (a <= m.limit - b)
                        offer({'+', a, b, a + b}, cost);
                    } else if (a != b)
                      offer({'-', max(a, b), min(a, b), a > b ? a - b : b - a}, cost);
                  };
                  if (it != pool.end())
                    check(*it);
                  if (it != pool.begin())
                    check(*prev(it));
                };
                if (a < n)
                  inspect(n / a, '*');
                if (a < n)
                  inspect(n - a, '+');
                if (a > n)
                  inspect(a - n, '-');
                if (a <= m.limit - n)
                  inspect(n + a, '-');
              }
            size_t take = min<size_t>(16, near.size());
            partial_sort(near.begin(), near.begin() + take, near.end(),
                         [](auto &a, auto &b) { return a.score < b.score; });
            for (size_t j = 0; j < take; ++j) {
              auto [score, e, q] = near[j];
              Path p;
              materialize(e.a, p);
              materialize(e.b, p);
              p.push_back(e);
              if (!q) {
                finish(std::move(p));
                continue;
              }
              p.push_back(e.v > n ? E{'-', e.v, q, n} : E{'+', e.v, q, n});
              propose(q, std::move(p));
            }
          }
          for (auto const &index : moduli) {
            U a = index.base;
            if (a >= n)
              continue;
            U rem = n % a;
            for (int sign : {1, -1}) {
              U residue = sign == 1 ? rem : (a - rem) % a;
              auto it = index.representative.find(residue);
              if (it == index.representative.end())
                continue;
              U r = it->second, prod = 0;
              if (sign == 1)
                prod = n >= r ? n - r : r - n;
              else if (n <= m.limit - r)
                prod = n + r;
              if (!prod || prod > m.limit)
                continue;
              U q = prod / a;
              if (!q || q >= n)
                continue;
              Path p;
              materialize(r, p);
              p.push_back({'*', a, q, prod});
              p.push_back(sign < 0 ? E{'-', prod, r, n}
                          : n >= r ? E{'+', prod, r, n}
                                   : E{'-', r, prod, n});
              propose(q, std::move(p));
            }
          }
          for (U a : radix) {
            if (a < 2 || a >= n)
              continue;
            for (int round = 0; round < 2; ++round) {
              U q = n / a + round;
              if (q == 0 || q > m.limit / a)
                continue;
              U prod = q * a;
              U r = prod > n ? prod - n : n - prod;
              if (r && !recipes.count(r))
                continue;
              Path p;
              materialize(a, p);
              if (r)
                materialize(r, p);
              p.push_back({'*', a, q, prod});
              if (r)
                p.push_back(prod > n ? E{'-', prod, r, n} : E{'+', prod, r, n});
              propose(q, std::move(p));
            }
          }
        }
        size_t width = min<size_t>(4, next.size());
        partial_sort(next.begin(), next.begin() + width, next.end(),
                     [](auto const &a, auto const &b) { return a.priority < b.priority; });
        next.resize(width);
        fringe = std::move(next);
      }
      return best;
    }
  };
  void run(bool stop_after_target = false, bool initialize = true) {
    if (initialize) {
      init();
      if (mode == 4)
        seed_odd_ladder();
    }
    while (true) {
      vector<U> remaining;
      for (U t : goals)
        if (!hit.count(t))
          remaining.push_back(t);
      if (remaining.empty())
        break;
      Book book(*this);
      vector<pair<double, U>> ranks;
      for (U n : remaining) {
        auto it = book.recipes.find(n);
        double score = it == book.recipes.end() ? 100 : it->second.cost;
        for (int c = 0; c < int(book.levels.size()); ++c) {
          auto &layer = book.levels[c];
          auto p = lower_bound(layer.begin(), layer.end(), n);
          if (p != layer.end())
            score = min(score, c + 1 + 0.18 * log2(double(*p - n) + 1));
          if (p != layer.begin())
            score = min(score, c + 1 + 0.18 * log2(double(n - *prev(p)) + 1));
        }
        ranks.emplace_back(score + noise() * 2, n);
      }
      sort(ranks.begin(), ranks.end());
      Path chosen;
      double price = 1e20;
      for (size_t i = 0; i < min<size_t>(3, ranks.size()); ++i) {
        auto p = book.solve(ranks[i].second);
        double cross = 0;
        if (mode)
          for (E e : p)
            if (e.v > 2)
              for (U t : remaining)
                if (t != ranks[i].second && t > e.v && t % e.v == 0)
                  cross += 0.07;
        double score = p.size() - min(cross, 1.5) + noise() * 0.7;
        if (score < price) {
          chosen = std::move(p);
          price = score;
        }
      }
      if (chosen.empty())
        throw runtime_error("target plan empty");
      emit(chosen);
      if (stop_after_target)
        return;
    }
  }
};
int main() {
  U lim, seed;
  int nr, n, k, mode;
  while (cin >> lim >> nr >> n >> k >> mode >> seed) {
    vector<U> s(n), g(k);
    for (U &a : s)
      cin >> a;
    for (U &a : g)
      cin >> a;
    Machine m(s, g, lim, nr, mode == 5 ? 2 : mode, seed);
    if (mode == 5) {
      m.run(true);
      for (int j = 1; j < 8; ++j) {
        Machine other(s, g, lim, nr, 2, seed + j);
        other.run(true);
        if (other.output.size() < m.output.size())
          m = std::move(other);
      }
      m.run(false, false);
    } else
      m.run();
    cout << m.output.size() << '\n';
    for (E e : m.output)
      cout << e.op << ' ' << e.a << ' ' << e.b << ' ' << e.v << '\n';
    cout.flush();
  }
}
