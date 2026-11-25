// Count targets and target pairs with a product of two dictionary entries.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <unordered_set>
#include <vector>

using U = std::uint64_t;

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    int k, n, rounds;
    while (std::cin >> k >> n >> rounds) {
        std::vector<U> factors(k), values(n);
        for (auto &a : factors) std::cin >> a;
        std::unordered_set<U> known(factors.begin(), factors.end());
        auto hit = [&](U v) {
            if (k == 0 || v < 4) return false;
            U largest = factors.back();
            auto begin = std::lower_bound(factors.begin(), factors.end(), (v-1)/largest + 1);
            U root = static_cast<U>(std::sqrt(static_cast<long double>(v)));
            while ((root+1)*(root+1)<=v) ++root;
            while (root*root>v) --root;
            for (auto it=begin; it!=factors.end() && *it<=root; ++it)
                if (v % *it == 0 && known.count(v / *it)) return true;
            return false;
        };
        for (int r=0; r<rounds; ++r) {
            for (auto &v : values) std::cin >> v;
            int direct=0, pairs=0;
            for (int j=0; j<n; ++j) {
                direct+=hit(values[j]);
                for (int i=0;i<j;++i) pairs+=hit(values[j]-values[i]);
            }
            std::cout << direct << ' ' << pairs << '\n';
        }
    }
}
