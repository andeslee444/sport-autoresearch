"""Sports Research Experiment — the ONLY file the agent modifies.

Contains parameter configurations that the backtest harness evaluates.
The agent tries different values; the harness reports metrics.
All values below are the current Oracle production defaults (hardcoded guesses).
"""

# ── Book B: Probability Adjustments ──────────────────────────────

# Matchup: opponent-specific performance shift
# Formula: clamp((opp_avg / season_avg - 1.0) * MULTIPLIER, -CAP, CAP)
MATCHUP_MULTIPLIER = 0.05
MATCHUP_CAP = 0.10

# Venue: home/away performance shift
# Formula: clamp((venue_avg / season_avg - 1.0) * MULTIPLIER, -CAP, CAP)
VENUE_MULTIPLIER = 0.10
VENUE_CAP = 0.05

# Back-to-back: second night penalty (fixed)
B2B_PENALTY = -0.05

# Recency weights for empirical hit rate
# Games sorted most-recent-first; index determines weight bucket
RECENCY_WEIGHT_LAST5 = 2.0     # Games 1-5 (most recent)
RECENCY_WEIGHT_LAST10 = 1.5    # Games 6-10
RECENCY_WEIGHT_SEASON = 1.0    # Games 11+

# Fallback sigma when no game data available (logistic approximation)
FALLBACK_SIGMA = 0.15

# Approach: True = shift raw stat values before counting hits (preserves
# distribution shape); False = count hits then shift probability (simpler)
USE_STAT_SPACE = False

# Testing scope: line offsets and extended stat types
# TEST_LINE_OFFSETS = [0] tests only at training-set mean
# TEST_LINE_OFFSETS = [-2, 0, 2] tests at mean-2, mean, mean+2 (3x samples)
TEST_LINE_OFFSETS = [0]

# USE_EXTENDED_STATS = True adds steals, blocks, turnovers, rebounds+assists
USE_EXTENDED_STATS = False

# ── Book C: Live Event Parameters ────────────────────────────────

# Foul trouble signal
FOUL_TROUBLE_PROB = 0.25
FOUL_TROUBLE_MINUTES_REDUCTION = 0.70

# Blowout signal
BLOWOUT_PROB = 0.15
BLOWOUT_MINUTES_THRESHOLD = 10.0
BLOWOUT_MINUTES_REDUCTION = 0.50

# Overtime-likely signal
OT_MINUTES = 5.0
OT_MARGIN_FACTOR_TIED = 1.0
OT_MARGIN_FACTOR_CLOSE = 0.55
OT_CLOCK_DECAY = 200.0
OT_BASE_MULTIPLIER = 0.80
OT_MAX_PROB = 0.85
OT_OVER_PROB_BASE = 0.50
OT_OVER_PROB_MULTIPLIER = 2.0
OT_OVER_PROB_MIN = 0.40
OT_OVER_PROB_MAX = 0.90
OT_NO_OT_PROB_BASE = 0.30
OT_NO_OT_PROB_MULTIPLIER = 2.0
OT_NO_OT_PROB_MIN = 0.10
OT_NO_OT_PROB_MAX = 0.80
OT_SAFETY_MARGIN = 1.05
OT_GAP_THRESHOLD = 0.30

# ── Edge Thresholds ──────────────────────────────────────────────

BOOK_A_MIN_EDGE = 0.15
BOOK_B_MIN_EDGE = 0.10
BOOK_C_MIN_EDGE = 0.12

# ── Position Sizing ──────────────────────────────────────────────

BOOK_A_SIZE_PCT = 0.02
BOOK_B_SIZE_PCT = 0.015
BOOK_C_SIZE_PCT = 0.01
