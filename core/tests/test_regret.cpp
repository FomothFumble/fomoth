// Unit tests for the regret engine. No framework: asserts print and set the exit code.
#include <cmath>
#include <cstdio>
#include <vector>

#include "fomoth/regret.hpp"

using namespace fomoth;

static int failures = 0;

static void approx(const char* name, double got, double want, double eps = 1e-6) {
    if (std::fabs(got - want) > eps) {
        std::printf("FAIL %s: got %.6f want %.6f\n", name, got, want);
        ++failures;
    } else {
        std::printf("ok   %s = %.6f\n", name, got);
    }
}

static void check(const char* name, bool cond) {
    if (!cond) {
        std::printf("FAIL %s\n", name);
        ++failures;
    } else {
        std::printf("ok   %s\n", name);
    }
}

int main() {
    // day0: high 2 close 1 | day1: high 10 close 3 | day2: high 5 close 4
    // suffix highs: [10, 10, 5]
    const std::vector<Candle> series = {{0, 2, 1}, {86400, 10, 3}, {172800, 5, 4}};

    // sell 100 on day0 at price 1, peak after = 10 -> 100 * 9 = 900
    // sell 50  on day2 at price 4, peak after = 5  ->  50 * 1 =  50
    const std::vector<Sell> sells = {{0, 100}, {172800, 50}};

    TokenRegret tr = token_regret("TKN", series, sells);
    approx("fumble_usd", tr.fumble_usd, 950.0);
    approx("sold_tokens", tr.sold_tokens, 150.0);
    approx("peak_mult", tr.peak_mult, 1.25);  // suffix at last sell day (5) / last price (4)
    check("priced", tr.priced);
    check("sells counted", tr.sells == 2);

    // no price history -> not priced, no fumble
    TokenRegret none = token_regret("NONE", {}, sells);
    check("empty not priced", !none.priced);
    approx("empty fumble", none.fumble_usd, 0.0);

    // build() sums and ranks by fumble descending
    std::vector<TokenInput> in;
    in.push_back({"A", series, sells});
    in.push_back({"B", series, std::vector<Sell>{{0, 10}}});  // 10 * (10 - 1) = 90
    RegretReport rep = build(in);
    approx("total_fumble", rep.total_fumble, 1040.0);
    check("priced count", rep.priced == 2);
    check("ranked by fumble", rep.tokens.front().mint == "A");

    std::printf(failures ? "\n%d FAILURE(S)\n" : "\nall regret tests passed\n", failures);
    return failures ? 1 : 0;
}
