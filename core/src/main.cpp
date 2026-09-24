// fumble: the FOMOTH regret engine as a small CLI.
//
// Reads a whitespace-separated description of a wallet's sells and daily price series
// from stdin and prints the regret report as JSON to stdout. It is what the Python
// layer shells out to for the heavy pass; the pure-Python path in fomoth/regret.py is
// the fallback when this binary is not built.
//
// Input grammar (all numbers whitespace-separated):
//
//     <num_tokens>
//     for each token:
//         <mint> <num_candles> <num_sells>
//         <num_candles lines>:  <ts> <high> <close>
//         <num_sells   lines>:  <ts> <tokens>
//
// Timestamps are unix seconds.
#include <cstdint>
#include <iostream>
#include <ostream>
#include <string>
#include <utility>
#include <vector>

#include "fomoth/regret.hpp"

namespace {

// Write a double with enough precision to round-trip, JSON-safe (no NaN/Inf).
void put_num(std::ostream& os, double v) {
    if (!(v == v) || v > 1e308 || v < -1e308) {  // NaN or Inf
        os << "0";
        return;
    }
    os.precision(12);
    os << v;
}

void put_str(std::ostream& os, const std::string& s) {
    os << '"';
    for (char c : s) {
        if (c == '"' || c == '\\') os << '\\';
        os << c;
    }
    os << '"';
}

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);

    std::size_t num_tokens = 0;
    if (!(std::cin >> num_tokens)) {
        std::cerr << "fumble: expected a token count on stdin\n";
        return 2;
    }

    std::vector<fomoth::TokenInput> input;
    input.reserve(num_tokens);

    for (std::size_t t = 0; t < num_tokens; ++t) {
        fomoth::TokenInput in;
        std::size_t nc = 0;
        std::size_t ns = 0;
        if (!(std::cin >> in.mint >> nc >> ns)) {
            std::cerr << "fumble: truncated token header at index " << t << "\n";
            return 2;
        }
        in.series.reserve(nc);
        for (std::size_t i = 0; i < nc; ++i) {
            fomoth::Candle c;
            if (!(std::cin >> c.ts >> c.high >> c.close)) {
                std::cerr << "fumble: truncated candle for " << in.mint << "\n";
                return 2;
            }
            in.series.push_back(c);
        }
        in.sells.reserve(ns);
        for (std::size_t i = 0; i < ns; ++i) {
            fomoth::Sell s;
            if (!(std::cin >> s.ts >> s.tokens)) {
                std::cerr << "fumble: truncated sell for " << in.mint << "\n";
                return 2;
            }
            in.sells.push_back(s);
        }
        input.push_back(std::move(in));
    }

    const fomoth::RegretReport rep = fomoth::build(input);

    std::ostream& os = std::cout;
    os << "{\"total_fumble\":";
    put_num(os, rep.total_fumble);
    os << ",\"priced\":" << rep.priced << ",\"tokens\":[";
    for (std::size_t i = 0; i < rep.tokens.size(); ++i) {
        const fomoth::TokenRegret& tr = rep.tokens[i];
        if (i) os << ',';
        os << "{\"mint\":";
        put_str(os, tr.mint);
        os << ",\"sold_tokens\":";
        put_num(os, tr.sold_tokens);
        os << ",\"fumble_usd\":";
        put_num(os, tr.fumble_usd);
        os << ",\"peak_mult\":";
        put_num(os, tr.peak_mult);
        os << ",\"sells\":" << tr.sells;
        os << ",\"priced\":" << (tr.priced ? "true" : "false");
        os << '}';
    }
    os << "]}\n";
    return 0;
}
