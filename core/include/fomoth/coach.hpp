// FOMOTH coach metrics (C++ core).
//
// The aggregate numbers behind the coaching: expectancy, payoff, win rate and the
// median hold times, computed from the wallet's per-token realized PnL. A faithful
// port of the metric block in fomoth/coach.py.
#pragma once

#include <vector>

namespace fomoth {

// One token's contribution to the aggregate: its realized PnL, the size (invested),
// and how long it was held. `has_hold` is false when the hold time is unknown.
struct CoachRow {
    double realized = 0.0;
    double size = 0.0;
    double hold_min = 0.0;
    bool has_hold = false;
};

struct CoachMetrics {
    double expectancy = 0.0;         // per-trade expected PnL
    double avg_win = 0.0;
    double avg_loss = 0.0;           // negative
    double payoff = 0.0;             // avg_win / |avg_loss|
    double win_rate = 0.0;           // percent
    double med_hold_min = 0.0;
    double med_win_hold_min = 0.0;
    double med_loss_hold_min = 0.0;
    int wins = 0;
    int losses = 0;
};

// Aggregate the rows. `win_pct_hint` overrides the computed win rate when >= 0 (the
// Python engine prefers the provider's own winPercentage when it has one).
CoachMetrics coach(const std::vector<CoachRow>& rows, double win_pct_hint = -1.0);

}  // namespace fomoth
