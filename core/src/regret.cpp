#include "fomoth/regret.hpp"

#include <algorithm>
#include <utility>

namespace fomoth {

namespace {
constexpr std::int64_t kDay = 86400;  // seconds in a day
}  // namespace

TokenRegret token_regret(const std::string& mint,
                         const std::vector<Candle>& series,
                         const std::vector<Sell>& sells) {
    TokenRegret tr;
    tr.mint = mint;
    tr.sells = static_cast<int>(sells.size());

    const std::size_t n = series.size();
    if (n == 0) return tr;  // no price history: cannot value the fumble
    tr.priced = true;

    // suffix[i] = the highest daily high from day i to the end, so "the peak after
    // day i" is an O(1) lookup once built.
    std::vector<double> suffix(n);
    suffix[n - 1] = series[n - 1].high;
    for (std::size_t i = n - 1; i-- > 0;) {
        suffix[i] = std::max(series[i].high, suffix[i + 1]);
    }

    // the timestamp column, for a lower_bound by day.
    std::vector<std::int64_t> ts(n);
    for (std::size_t i = 0; i < n; ++i) ts[i] = series[i].ts;

    std::int64_t last_sell_ts = -1;
    double last_sell_price = 0.0;

    for (const auto& s : sells) {
        const std::int64_t day = s.ts - (s.ts % kDay);
        std::size_t j = static_cast<std::size_t>(
            std::lower_bound(ts.begin(), ts.end(), day) - ts.begin());
        if (j >= n) j = n - 1;

        const double price_at = series[j].close > 0.0 ? series[j].close : series[j].high;
        const double peak_after = suffix[j];

        tr.sold_tokens += s.tokens;
        tr.fumble_usd += s.tokens * std::max(0.0, peak_after - price_at);

        if (s.ts > last_sell_ts) {
            last_sell_ts = s.ts;
            last_sell_price = price_at;
        }
    }

    if (last_sell_price > 0.0) {
        const std::int64_t day = last_sell_ts - (last_sell_ts % kDay);
        std::size_t k = static_cast<std::size_t>(
            std::lower_bound(ts.begin(), ts.end(), day) - ts.begin());
        if (k >= n) k = n - 1;
        tr.peak_mult = suffix[k] / last_sell_price;
    }
    return tr;
}

RegretReport build(const std::vector<TokenInput>& input) {
    RegretReport rep;
    rep.tokens.reserve(input.size());
    for (const auto& in : input) {
        TokenRegret tr = token_regret(in.mint, in.series, in.sells);
        if (tr.priced) ++rep.priced;
        rep.total_fumble += tr.fumble_usd;
        rep.tokens.push_back(std::move(tr));
    }
    std::sort(rep.tokens.begin(), rep.tokens.end(),
              [](const TokenRegret& a, const TokenRegret& b) {
                  return a.fumble_usd > b.fumble_usd;
              });
    return rep;
}

}  // namespace fomoth
