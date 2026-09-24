// Unit tests for the coach metrics.
#include <cmath>
#include <cstdio>
#include <vector>

#include "fomoth/coach.hpp"

using namespace fomoth;

static int failures = 0;

static void approx(const char* name, double got, double want, double eps = 1e-4) {
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
    std::vector<CoachRow> rows;
    rows.push_back({100.0, 500.0, 10.0, true});  // win
    rows.push_back({-50.0, 400.0, 20.0, true});  // loss
    rows.push_back({30.0, 300.0, 30.0, true});   // win

    CoachMetrics m = coach(rows);

    check("wins", m.wins == 2);
    check("losses", m.losses == 1);
    approx("avg_win", m.avg_win, 65.0);
    approx("avg_loss", m.avg_loss, -50.0);
    approx("payoff", m.payoff, 1.3);
    approx("win_rate", m.win_rate, 66.6667);
    approx("expectancy", m.expectancy, 26.6667);
    approx("med_hold_min", m.med_hold_min, 20.0);
    approx("med_win_hold_min", m.med_win_hold_min, 20.0);   // median(10, 30)
    approx("med_loss_hold_min", m.med_loss_hold_min, 20.0);  // median(20)

    // a provider hint overrides the computed win rate
    CoachMetrics h = coach(rows, 40.0);
    approx("win_rate hint", h.win_rate, 40.0);
    approx("expectancy hint", h.expectancy, 0.40 * 65.0 + 0.60 * -50.0);

    std::printf(failures ? "\n%d FAILURE(S)\n" : "\nall coach tests passed\n", failures);
    return failures ? 1 : 0;
}
