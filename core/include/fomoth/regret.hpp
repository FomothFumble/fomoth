// FOMOTH regret engine (C++ core).
//
// The heavy part of the report: for every token the wallet sold, how much money was
// left on the table. For each sell we value the tokens against the highest price the
// token reached *after* that sell, summed across every sell of every token.
//
//     fumble_usd(sell) = tokens_sold * max(0, peak_high_after_sell - price_at_sell)
//
// A faithful C++ port of fomoth/regret.py (suffix-max of daily highs + binary search
// per sell), kept fast because it runs over the whole trade history of a wallet.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace fomoth {

// One daily candle. `ts` is a unix timestamp in seconds (day-aligned upstream).
struct Candle {
    std::int64_t ts = 0;
    double high = 0.0;
    double close = 0.0;
};

// One sell of a token. `ts` in seconds, `tokens` is the amount sold.
struct Sell {
    std::int64_t ts = 0;
    double tokens = 0.0;
};

// The regret computed for a single token.
struct TokenRegret {
    std::string mint;
    double sold_tokens = 0.0;
    double fumble_usd = 0.0;  // left on the table across all sells
    double peak_mult = 0.0;   // peak after your last sell vs your last sell price
    int sells = 0;
    bool priced = false;      // did we have price history for it
};

// One token's inputs: its daily series (sorted ascending by ts) and its sells.
struct TokenInput {
    std::string mint;
    std::vector<Candle> series;
    std::vector<Sell> sells;
};

// The full wallet-level regret result, tokens ranked by fumble descending.
struct RegretReport {
    std::vector<TokenRegret> tokens;
    double total_fumble = 0.0;
    int priced = 0;  // how many tokens had usable price history
};

// Regret for one token. `series` must be sorted ascending by ts.
TokenRegret token_regret(const std::string& mint,
                         const std::vector<Candle>& series,
                         const std::vector<Sell>& sells);

// Regret across a whole wallet.
RegretReport build(const std::vector<TokenInput>& input);

}  // namespace fomoth
