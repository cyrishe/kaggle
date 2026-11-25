// Enumerate every legal operation on two F2 values, keeping one recipe per distinct value.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>

struct Entry { uint64_t value; uint32_t recipe; };
int main(int argc, char** argv) {
    size_t n;
    uint64_t limit;
    if (argc != 3 || !(std::cin >> n >> limit) || !n || n >= 16384) return 1;
    std::vector<uint64_t> values(n);
    for (auto& v : values) if (!(std::cin >> v) || !v || v>limit) return 1;
    std::vector<Entry> entries;
    entries.reserve(3*n*(n+1)/2);
    for (size_t i=0; i<n; ++i) {
        for (size_t j=0; j<=i; ++j) {
            uint64_t a=std::max(values[i],values[j]), b=std::min(values[i],values[j]);
            uint32_t code=(i<<16)|(j<<2);
            if (a<=limit-b) entries.push_back({a+b,code});
            if (a>b) entries.push_back({a-b,code+1});
            if (a<=limit/b) entries.push_back({a*b,code+2});
            if (a%b==0) entries.push_back({a/b,code+3});
        }
    }
    std::sort(entries.begin(),entries.end(),[](Entry a, Entry b) {
        return a.value<b.value || (a.value==b.value && a.recipe<b.recipe);
    });
    std::ofstream keys(argv[1],std::ios::binary), recipes(argv[2],std::ios::binary);
    uint64_t previous=0;
    size_t count=0;
    for (const auto& e:entries) if (e.value!=previous) {
        keys.write(reinterpret_cast<const char*>(&e.value),sizeof(e.value));
        recipes.write(reinterpret_cast<const char*>(&e.recipe),sizeof(e.recipe));
        previous=e.value;
        ++count;
    }
    keys.close(); recipes.close();
    if (!keys || !recipes) return 2;
    std::cout<<count<<'\n';
}
