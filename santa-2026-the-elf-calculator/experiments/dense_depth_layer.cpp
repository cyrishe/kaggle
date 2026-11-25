// Read a sorted cumulative layer and mark its next layer with one bit per value.
// Used only for instances whose bounded integer universe fits the supplied memory budget.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc, char** argv) {
    uint64_t limit;
    size_t count;
    if (argc != 2 || !(std::cin >> limit >> count) || limit > 2000000000) return 2;
    std::vector<uint64_t> values(count), bits(limit / 64 + 1);
    auto mark = [&](uint64_t x) { bits[x / 64] |= uint64_t{1} << (x % 64); };
    for (auto &x : values) {
        if (!(std::cin >> x) || x == 0 || x > limit) return 2;
        mark(x);
    }
    if (!std::is_sorted(values.begin(), values.end())) return 2;
    for (size_t i=0; i<count; ++i) {
        uint64_t a=values[i];
        for (size_t j=0; j<=i; ++j) {
            uint64_t b=values[j];
            if (a+b <= limit) mark(a+b);
            if (a>b) mark(a-b);
            if (a*b <= limit) mark(a*b);
            if (a%b==0) mark(a/b);
        }
    }
    uint64_t total=0;
    for (uint64_t word:bits) total+=__builtin_popcountll(word);
    std::ofstream out(argv[1], std::ios::binary);
    out.write(reinterpret_cast<const char*>(bits.data()), bits.size()*sizeof(uint64_t));
    if (!out) return 1;
    std::cout << total << '\n';
}
