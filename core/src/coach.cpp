#include "fomoth/coach.hpp"

#include <algorithm>
#include <vector>

namespace fomoth {

namespace {

// Median of a copy of the values (0 for an empty set), matching statistics.median:
// the mean of the two middle values on an even count.
double median(std::vector<double> xs) {
    if (xs.empty()) return 0.0;
    std::sort(xs.begin(), xs.end());
    const std::size_t n = xs.size();
    if (n % 2 == 1) return xs[n / 2];
    return 0.5 * (xs[n / 2 - 1] + xs[n / 2]);
}

}  // namespace

CoachMetrics coach(const std::vector<CoachRow>& rows, double win_pct_hint) {
    CoachMetrics m;

    std::vector<double> wins;
    std::vector<double> losses;
    std::vector<double> win_holds;
    std::vector<double> loss_holds;
    std::vector<double> all_holds;

    for (const auto& r : rows) {
        const bool win = r.realized > 0.0;
        if (win) {
            wins.push_back(r.realized);
        } else if (r.realized < 0.0) {
            losses.push_back(r.realized);
        }
        if (r.has_hold) {
            all_holds.push_back(r.hold_min);
            if (win) {
                win_holds.push_back(r.hold_min);
            } else {
                loss_holds.push_back(r.hold_min);
            }
        }
    }

    m.wins = static_cast<int>(wins.size());
    m.losses = static_cast<int>(losses.size());

    double sum_win = 0.0;
    for (double x : wins) sum_win += x;
    double sum_loss = 0.0;
    for (double x : losses) sum_loss += x;

    m.avg_win = wins.empty() ? 0.0 : sum_win / static_cast<double>(wins.size());
    m.avg_loss = losses.empty() ? 0.0 : sum_loss / static_cast<double>(losses.size());
    m.payoff = m.avg_loss != 0.0 ? m.avg_win / -m.avg_loss : 0.0;

    const std::size_t n = rows.empty() ? 1 : rows.size();
    m.win_rate = win_pct_hint >= 0.0
                     ? win_pct_hint
                     : static_cast<double>(wins.size()) / static_cast<double>(n) * 100.0;

    const double p = m.win_rate / 100.0;
    m.expectancy = p * m.avg_win + (1.0 - p) * m.avg_loss;

    m.med_hold_min = median(all_holds);
    m.med_win_hold_min = median(win_holds);
    m.med_loss_hold_min = median(loss_holds);
    return m;
}

}  // namespace fomoth
