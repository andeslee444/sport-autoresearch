# The Oracle: NBA Hybrid Trading Strategy for Kalshi

> **Date**: 2026-03-17
> **Status**: Design approved, pending implementation
> **Scope**: NBA-focused, model-informed speed trading on Kalshi using Real Sports App as data source
> **Capital**: $1-5k bankroll, $30-100/trade, max 12 simultaneous positions
> **Supersedes**: Risk parameters in `KALSHI_MAPPING.md` Section "Risk Management Parameters" — this spec is the source of truth for all strategy configuration.

---

## 1. Overview

The Oracle is a three-layer hybrid trading system that combines deep statistical modeling with real-time live game signals to trade NBA prediction markets on Kalshi. Real Sports App provides the data (player stats, live feeds, momentum signals); Kalshi provides the execution venue.

**Edge theory**: Model-informed speed. The model computes fair value for every market using information most Kalshi traders don't have (per-opponent splits, pace matchups, recency-weighted averages). Real-time signals from Real's WebSocket confirm the thesis and time the entry.

**Trading universe**: NBA only (deepest data + only sport with Kalshi player props).

---

## 2. Market Universe

### Player Props (Primary — fattest edge)

| Kalshi Series | Prop | Real Data Advantage |
|---|---|---|
| `KXNBAPTS` | Points O/U | Splits (last 5/10/20), per-opponent, home/away, pace |
| `KXNBAREB` | Rebounds O/U | Per-opponent (some teams give up boards), position matchup |
| `KXNBAAST` | Assists O/U | Pace, teammate availability, per-opponent |
| `KXNBA3PT` | 3-Pointers O/U | Last-5 shooting splits, opponent 3PT defense ranking |
| `KXNBA2D` | Double-Double | Combined splits analysis (pts+reb or pts+ast trending) |
| `KXNBA3D` | Triple-Double | Only bet when splits show all three stats trending high |
| `KXNBABLK` | Blocks O/U | Per-opponent, rim protection matchup |
| `KXNBASTL` | Steals O/U | Per-opponent, pace-adjusted |

### Game-Level (Secondary — wider markets, thinner edge)

| Kalshi Series | Market | Real Data Advantage |
|---|---|---|
| `KXNBAGAME` | Game Winner | Team rankings, H2H, home/away records, momentum |
| `KXNBASPREAD` | Spread | Same + live score differential tracking |
| `KXNBATOTAL` | Total O/U | Team pace data, recent scoring trends |
| `KXNBATEAMTOTAL` | Team Total | Pace + opponent defensive rating |
| `KXNBA1HWINNER` | 1st Half Winner | Early momentum signals, Q1 trends |
| `KXNBA2HWINNER` | 2nd Half Winner | Halftime adjustment patterns, Q3 momentum |

---

## 3. Layer 1 — Pre-Game Prior Model

Runs 1-2 hours before tip-off. Computes fair value probability for every player prop and game market on tonight's slate.

### 6-Factor Model for Player Props

```
P(over) = f(baseline, recency, opportunity, matchup, situational, correlated_markets)
```

**Model type**: Linear weighted average of per-factor probabilities as a v1 heuristic. This is NOT a proper probability model — a linear blend of probabilities is not guaranteed to be well-calibrated. In v2, migrate to log-odds blending (convert each factor to log-odds, weighted average, convert back) or logistic regression. In v1, apply Platt scaling (a sigmoid calibration layer) trained on the first 200+ trades to correct for systematic over/under-confidence.

#### Factor 1: Baseline (15% weight)

- **What**: Player's season average for this stat
- **Source**: Real player profile `seasonStats` via `GET /players/{id}/sport/nba?season=2025`
- **Purpose**: Anchor. Kalshi already prices near this — our edge comes from the other factors.

#### Factor 2: Recency (25% weight)

- **What**: Last-5 game average (last-3 for volatile stats: 3PT, blocks, steals)
- **Source**: Real splits `averages` for "Last 5" / "Last 3" periods
- **Purpose**: Captures streakiness. The "hot hand" is real (Miller & Sanjurjo 2018). Markets underweight recency by anchoring to season averages.
- **Computation**: Empirical hit rate — how many of the last N games did the player clear this line?

#### Factor 3: Opportunity (25% weight)

Composite of four sub-factors that determine how many chances the player gets tonight:

**a) Projected Minutes**
- Player's recent minutes average from splits data
- Source: Real player profile splits — the `SplitRow` for "Last 5" or "Last 10" should include a `min` or `minutes` stat in the `stats` record. **Technical risk**: If minutes are NOT in the splits, fallback to fetching last 5 box scores via `GET /playerboxscores/{id}?version=2` and averaging the minutes field. This fallback costs ~5 API calls per player (50-100 total calls pre-game for a full slate). Budget this into the pre-game data fetch.
- Back-to-back adjustment: -2 to -5 minutes on second night of B2B
- Source for B2B detection: Real schedule `GET /home/nba/days?type=condensed`
- Every +1 minute played = ~0.7 more points for a starter

**b) Pace**
- How fast do both teams play? High-pace game (110 possessions) = ~15% more counting stats than low-pace (95 possessions)
- Source: Real team stat leaders + Kalshi's game total market as proxy
- Single most underpriced factor in player props

**c) Usage Boost (Teammate Availability)**
- Key teammate OUT → player's usage rate increases → more shots → more points (fewer assists)
- Source: Real player status (Active/Out/Questionable) for all roster players
- Effect: +2-4 points when a team's #2 scorer is out

**d) Blowout Risk**
- Spread > 10 points → favorite's starters may sit Q4 (lose ~8 minutes)
- Source: Kalshi spread market `KXNBASPREAD`
- Negative predictor: high blowout risk → fewer minutes → lower stats

#### Factor 4: Matchup Quality (20% weight)

Two sub-components:

**a) Player vs. Opponent History**
- Source: Real per-opponent splits (included in player profile)
- Primary if >= 3 games of data, else fallback to (b)

**b) Opponent Defensive Ranking for This Stat**
- Source: Real `GET /teamstatleaders/nba/seasons/2025/seasontypes/regularseason/stats/{statId}`
- Bottom-5 defense for this stat category → adjust +8-12%
- Top-5 defense → adjust -8-12%
- **statId discovery**: Query `GET /teamstatleaders/nba/seasons` first to retrieve the list of available stat categories and their numeric IDs. Cache this mapping at startup. Expected mappings (must be verified at runtime):

| Stat Name | Expected statId | Used For |
|---|---|---|
| Points Per Game | TBD | Points prop matchup |
| Rebounds Per Game | TBD | Rebounds prop matchup |
| Assists Per Game | TBD | Assists prop matchup |
| 3-Pointers Per Game | TBD | 3PT prop matchup |
| Blocks Per Game | TBD | Blocks prop matchup |
| Steals Per Game | TBD | Steals prop matchup |
| Opponent Points Per Game | TBD | Defensive rating |

#### Factor 5: Situational (10% weight)

- **Home/away**: +1.5 pts at home on average. Source: Real splits home/away averages.
- **Rest**: Back-to-back = -2 to -3 pts on average. Source: Computed from Real schedule.
- **Game importance**: Teams in playoff race play starters more. Source: Real standings clinch/elimination status.

#### Factor 6: Correlated Markets (5% weight)

Use other Kalshi market prices as inputs:
- Game total (O/U 235 implies high-scoring → inflate all point props)
- Team total (LAL over 118.5 at $0.70 → LAL players will score a lot)
- Spread (proxy for blowout risk, already in Opportunity, but price gives market's confidence)

### Game-Level Model

For game winner, spread, and total markets:

```
P(home_win) = logistic_regression(
  team_season_ranking,        # Real: /rankings/sport/nba/entity/team/ranking/primary
  team_7day_ranking,          # Real: /rankings/.../tertiary
  home_court_advantage,       # Real: team standings home/away records
  recent_h2h,                 # Real: last 3 matchups
  key_player_availability,    # Real: player status Active/Out/Questionable
  streak,                     # Real: team standings streak (W5, L2)
  rest_advantage              # Real: schedule (one team on B2B, other rested)
)
```

### Example Calculation

```
Player: LeBron James | Stat: Points | Line: 27.5

Baseline     (15%):  Season avg 27.1 → ~50% at 27.5
Recency      (25%):  Last-5 avg 31.2, cleared 4/5 → 80%
Opportunity  (25%):  Home (full min), no B2B, fast pace matchup,
                      no teammate out, spread -4.5 (no blowout) → 75%
Matchup      (20%):  34.5 avg vs HOU (2 games), HOU 25th defense → 82%
Situational  (10%):  Home, not B2B, playoff race → 68%
Correlated    (5%):  Game total O/U 232, over at $0.62 → 65%

Raw P(over)  = 0.15(0.50) + 0.25(0.80) + 0.25(0.75) + 0.20(0.82)
             + 0.10(0.68) + 0.05(0.65)
             = 0.727 (72.7%)

Calibrated P = platt_sigmoid(0.727) → ~0.73 (after calibration layer)

Kalshi YES price: $0.60
Kalshi fee on win: ~$0.04 (see Fees section)
Net edge: 0.73 - 0.60 - (0.73 * 0.04) = $0.101 (10.1 cents net)
Gross edge: 0.73 - 0.60 = $0.13 (13 cents gross)
→ SIGNAL: BUY YES (gross edge > 12 cent threshold)
```

---

## 4. Layer 2 — Live Bayesian Update Engine

Once the game tips off, the engine updates probability every time a play event comes through Real's WebSocket.

### Core: Pace-Adjusted Projection

```python
from scipy.stats import norm

# Base standard deviation per stat type (calibrate from historical data)
BASE_STD_DEV = {
    'pts': 8.5,    # NBA player point totals have ~8.5 std dev
    'reb': 3.2,    # Rebounds
    'ast': 2.8,    # Assists
    '3pt': 1.5,    # 3-pointers made
    'blk': 1.0,    # Blocks
    'stl': 0.9,    # Steals
}

REGULATION_MINUTES = 48  # NBA regulation; add 5 per OT period

def update_probability(player, stat, line, game_state, overtimes=0):
    current = player.live_stats[stat]
    minutes_played = player.minutes_played
    total_game_minutes = REGULATION_MINUTES + (overtimes * 5)
    minutes_remaining = estimate_remaining_minutes(
        game_period, game_clock, game_state, player.fouls,
        total_game_minutes
    )

    # Use tonight's rate if enough sample, else season rate
    if minutes_played > 8:
        rate_tonight = current / minutes_played
    else:
        rate_tonight = player.season_per_minute_rate

    projected = current + (rate_tonight * minutes_remaining)

    # Standard deviation shrinks as game progresses (less time = less variance)
    # Use sqrt for proper variance scaling over time
    base_std = BASE_STD_DEV.get(stat, 5.0)
    std_dev = base_std * (minutes_remaining / total_game_minutes) ** 0.5

    # Normal distribution CDF for probability
    # Note: norm.cdf `scale` parameter is standard deviation, NOT variance
    p_over = 1 - norm.cdf(line, loc=projected, scale=max(std_dev, 0.1))
    return p_over
```

### Adjustment 1: Time-Weighted Production Rate

NBA scoring distribution across quarters:
- Q1: ~24%, Q2: ~26%, Q3: ~25%, Q4: ~25%
- Close games Q4: ~28% (stars take over)
- Blowouts Q4: ~12% (bench minutes)

### Adjustment 2: Foul Trouble Detection

```
4 fouls before Q4 → projected_minutes * 0.75
5 fouls any time  → projected_minutes * 0.50 (foul-out risk)
```

**Source**: Primary: `LiveFeedSocketPlayersUpdated` WebSocket event — check if `personalFouls` or `pf` field exists in the player stats payload. **Technical risk**: The exact schema of this event is not confirmed to include foul data. **Fallback**: If fouls are not in the WebSocket payload, detect fouls by parsing play-by-play event descriptions from `LiveFeedSocketPlaysAdded` (look for "foul" in the `description` field and track a local counter). Secondary fallback: poll `GET /playerboxscores/{id}?version=2` every 60 seconds during games.

### Adjustment 3: Game Flow State Machine

| State | Condition | Effect on Projections |
|---|---|---|
| COMPETITIVE | Margin < 10 | Normal projection. Stars play full minutes. |
| BLOWOUT_FOR | Team +15 | Star sits Q4. REDUCE stats. Sell overs. |
| BLOWOUT_AGN | Team -15 | High variance. Star may sit or go hero mode. Don't trade. |
| CLUTCH | Close game, Q4 < 5 min | Stars get all touches. INCREASE pts/ast for primary scorers. |
| OVERTIME | Tied, < 2 min or OT started | +15% stat boost for starters. Buy overs BEFORE OT starts. Reset minutes_remaining to include OT period (5 min). |

### Prior-to-Live Blending Weights

| Game Phase | Pre-Game Prior | Live Update |
|---|---|---|
| Game start | 100% | 0% |
| End Q1 | 60% | 40% |
| Halftime | 30% | 70% |
| End Q3 | 10% | 90% |
| Q4 < 5 min | 0% | 100% |

### Killer Signals (Largest Live Edges)

| Signal | Detection Source | Why Kalshi Lags | Edge |
|---|---|---|---|
| Star 4th foul in Q3 | PlayersUpdated / play-by-play text | Traders aren't tracking fouls | 15-25 cents |
| Overtime likely | Score tied, < 2 min | OT not priced until it happens | 10-20 cents |
| Blowout developing | +15 margin in Q3 | Star minutes cut not priced | 10-15 cents |
| Player hot start | 15+ pts in Q1 | Market anchors to season line | 12-18 cents |
| Teammate ejected/injured | PlayersUpdated | Usage redistribution not instant | 10-15 cents |
| Clutch mode | Competitive, Q4 < 5 min | Star usage spike not priced | 8-12 cents |

---

## 5. Layer 3 — Execution Engine

### Price Convention

All internal calculations use **decimal probability (0.00-1.00)**. Kalshi's API uses **integer cents (1-99)** for `yes_price`. Conversion:
- Internal → Kalshi: `yes_price_cents = int(internal_price * 100)`
- Kalshi → Internal: `internal_price = yes_price_cents / 100`

All code examples in this spec use internal decimal format unless noted otherwise.

### Execution Pipeline

```
Model P(over) update
  → Edge calculation (model_prob - kalshi_price)
  → Subtract expected fee to get net edge
  → Net edge > 12 cents? (min threshold)
  → Confidence filter (>= 2 of 3 strong factors agree)
  → Portfolio check (within all risk limits)
  → Position sizing (half-Kelly on net edge, capped)
  → Order placement (limit first, re-price up to 3x)
```

### Kalshi Fee Structure

Kalshi charges fees **on settlement of winning contracts only**:

| Contract Settlement Price | Fee per Contract |
|---|---|
| $0.01 - $0.10 | $0.01 |
| $0.11 - $0.20 | $0.02 |
| $0.21 - $0.30 | $0.03 |
| $0.31 - $0.40 | $0.04 |
| $0.41 - $0.50 | $0.05 |
| $0.51 - $0.60 | $0.06 |
| $0.61 - $0.99 | $0.07 |

> **Note**: Verify current fee schedule at runtime via Kalshi docs. Fees apply only to winning side. Losing contracts cost $0 in fees (you just lose the premium).

**Net edge formula**:
```python
gross_edge = model_prob - kalshi_price
expected_fee = model_prob * fee_for_price(1.0 - kalshi_price)  # fee on winning
net_edge = gross_edge - expected_fee
```

The 12-cent min threshold applies to **gross edge** (simpler, slightly conservative since expected fee is typically 2-5 cents). This means effective net edge is ~7-10 cents minimum.

### Position Sizing: Half-Kelly Criterion

```python
def calculate_position_size(edge, kalshi_price, side, bankroll):
    # Fee adjustment: reduce win payout by expected fee
    if side == 'yes':
        settlement_price = 1.0 - kalshi_price
        fee = fee_for_price(settlement_price)
        win_payout = (1.0 - kalshi_price) - fee  # net of fee
        loss_amount = kalshi_price
        model_prob = kalshi_price + edge
    else:
        settlement_price = kalshi_price
        fee = fee_for_price(settlement_price)
        win_payout = kalshi_price - fee  # net of fee
        loss_amount = 1.0 - kalshi_price
        model_prob = (1.0 - kalshi_price) + edge

    b = win_payout / loss_amount
    p = model_prob
    q = 1 - p

    full_kelly = (p * b - q) / b
    half_kelly = full_kelly / 2

    # Convert to contract count
    cost_per_contract = kalshi_price if side == 'yes' else (1.0 - kalshi_price)
    contracts = int((bankroll * half_kelly) / cost_per_contract)

    # Apply hard caps (percentage-based, see Risk Management)
    max_contracts = int(bankroll * MAX_SINGLE_MARKET_PCT / cost_per_contract)
    contracts = min(contracts, max_contracts)
    contracts = max(contracts, 0)
    return contracts
```

### Order Strategy

1. **Limit order first** at current best ask (or 1 cent below for maker rebate)
2. **Wait 30 seconds** for fill
3. **Re-price up to 3 times** at new ask if not filled
4. **Never chase**: if price moved 5+ cents toward model value, recalculate edge
5. **Time-sensitive signals** (foul trouble, OT imminent) get **market orders** immediately

### Exit Rules

| Rule | Trigger | Action |
|---|---|---|
| Thesis invalidated | Model probability drops below Kalshi price | Sell at current bid, take small loss |
| Lock in profit | Model > 92% AND Kalshi > $0.88 | Sell at current bid |
| Game state changed | Blowout develops while holding overs | Sell all affected positions |
| Hold to settlement | Default | Let binary contract settle at $1 or $0 |

---

## 6. Risk Management

### Hard Limits (Never Violated)

All percentage-based limits are computed dynamically from current bankroll. Dollar amounts shown assume $2k bankroll as example.

| Parameter | Limit | Example ($2k) | Rationale |
|---|---|---|---|
| Max simultaneous positions | 12 | 12 | Manageable complexity |
| Max total capital at risk | 40% of bankroll | $800 | Survive worst-case night |
| Max single market exposure | 4% of bankroll | $80 | No single bet kills you |
| Max exposure per game | 10% of bankroll | $200 | Correlated risk — game goes wrong, all props lose |
| Max exposure per player | 6% of bankroll | $120 | Single injury wipes all their props |
| Daily stop-loss | 7.5% of bankroll | -$150 | Stop trading, review model |
| Min edge to enter (gross) | $0.12 (12 cents) | — | Covers fees + noise |
| Min edge for market order | $0.18 (18 cents) | — | Need bigger edge to pay spread |
| Min confidence | 2 of 3 strong factors agree | — | Avoid single-factor bets |

### Correlation Guards

- Never hold YES on both sides of a spread (e.g., LAL winner AND HOU +5.5)
- Reduce position size by 30% when holding multiple props for same player (pts + reb + ast are correlated)
- Reduce position size by 20% when holding 3+ props in same game (all affected by OT, blowout)
- Track implied correlation: if 4 positions all need the same game to be high-scoring, that's concentrated risk — enforce per-game cap

---

## 7. Player & Market Matching

### Discovering Tonight's Players

The system needs to know which players are in tonight's games and their Real player IDs.

**Primary approach**:
1. Fetch tonight's schedule from Real: `GET /home/nba/next?cohort=0` — returns tonight's games with team info
2. Fetch stat trackers: `GET /stattrackers?day={today}&sport=nba` — returns player names with prop lines for today's games
3. Maintain a local **player lookup table** (SQLite) mapping `{player_name, team}` → `{real_player_id}`. Populated incrementally: when a new player name appears in stat trackers, search via `GET /players/sport/nba/search?season=2025` to find their ID. Cache permanently (player IDs don't change).

**Pre-game data fetch volume** (per game night with ~6 games, ~15 players per game):
- 1 call: tonight's schedule
- 1 call: stat trackers for the day
- ~90 calls: player profiles (15 players x 6 games, cached 5 min)
- ~12 calls: team data (6 games x 2 teams, cached 15 min)
- Total: ~104 calls, at 200ms each = ~21 seconds sequential. Well within rate limits.

### Matching Real Players to Kalshi Tickers

Kalshi player prop tickers encode player names in abbreviated form:
```
KXNBAPTS-26MAR18-LALLEBRONJ25-27
         │        │  │       │
         │        │  │       └── Line value
         │        │  └── Abbreviated player name
         │        └── Team abbreviation
         └── Date
```

**Matching strategy**:
1. Query Kalshi `GET /markets?series_ticker=KXNBAPTS&status=open` — each market has a `title` and `subtitle` field containing the full player name (e.g., "LeBron James Over 27.5 Points")
2. Parse the full player name from the Kalshi market title
3. Fuzzy match to Real's player names (handle Jr./III, hyphenated names, nicknames)
4. Store the mapping `{real_player_id}` → `{kalshi_ticker_pattern}` in the local lookup table
5. Refresh mapping daily (new players, line changes)

**Edge cases**: Players with identical last names on the same team (rare in NBA). Handle by including first name initial in the match. Log any ambiguous matches for manual review.

---

## 8. Daily Operating Cycle

```
T-2 hours (before first game):
  ├── Fetch tonight's slate from Kalshi + Real
  ├── Discover player IDs (lookup table + search fallback)
  ├── Pull player profiles, splits, team data from Real
  ├── Discover statId mappings (if not cached)
  ├── Match Real players to Kalshi tickers
  ├── Run Layer 1 pre-game model for all markets
  ├── Identify edges > 12 cents
  ├── Queue pre-game limit orders
  └── Log all model outputs

T-0 (tip-off):
  ├── Open Socket.io connection to Real (LiveFeed + PlayerBoxScore)
  ├── Start Kalshi price polling (every 5-10 seconds)
  ├── Layer 2 live engine activates
  └── Reassess unfilled pre-game orders

T+ongoing (during games):
  ├── Every play event → update projections
  ├── Every Kalshi poll → recalculate edges
  ├── Execute when pipeline passes all checks
  ├── Monitor positions for exit signals
  └── Enforce risk limits continuously

T+final (games end):
  ├── Positions settle on Kalshi ($1 or $0)
  ├── Record results: predicted edge vs actual outcome
  ├── Update calibration log
  └── Generate daily P&L report

Weekly:
  ├── Recalibrate factor weights from results
  ├── Re-train Platt scaling sigmoid on accumulated data
  ├── Adjust min edge threshold if win rate is off
  └── Review signal profitability by type
```

---

## 9. Key Statistical Correlations Exploited

| Correlation | Direction | Trading Implication |
|---|---|---|
| Pace ↔ All counting stats | Strong positive | High-pace games inflate points, rebounds, assists |
| Minutes ↔ All counting stats | Strongest predictor | +1 min = ~0.7 pts, ~0.3 reb, ~0.2 ast |
| Teammate absence ↔ Usage | Positive for pts, negative for ast | Buy points over, sell assists over |
| Blowout risk ↔ Star minutes | Strong negative | Sell the over on heavy favorites |
| Back-to-back ↔ Performance | Moderate negative (-5-8%) | Discount all props on B2B |
| 3PT rate ↔ Rebound variance | Moderate negative | More 3s = fewer offensive rebounds |
| Home court ↔ Points | Weak positive (+1.5 pts) | Consistent, compounds with other factors |
| Opponent pace ↔ Player stats | Strong positive | Fast opponent = more possessions for both |

---

## 10. Data Sources Summary

### Real Sports App (Signal Source)

| Data | Endpoint | Frequency | Purpose |
|---|---|---|---|
| Player profile + splits | `GET /players/{id}/sport/nba?season=2025` | Pre-game (cache 5 min) | Layer 1 factors 1-5 |
| Player box scores | `GET /playerboxscores/{id}?version=2` | Pre-game (fallback for minutes) | Minutes avg if not in splits |
| Player search | `GET /players/sport/nba/search?season=2025` | On new player discovery | Populate player ID lookup |
| Team standings | `GET /teamstandings/sport/nba/...` | Pre-game (cache 15 min) | Situational factor |
| Team rankings | `GET /rankings/sport/nba/entity/team/ranking/{period}` | Pre-game (cache 5 min) | Game-level model |
| Player rankings | `GET /rankings/sport/nba/entity/player/ranking/{period}` | Pre-game (cache 5 min) | Recency signal |
| Team stat leaders | `GET /teamstatleaders/nba/seasons/2025/...` | Pre-game (cache 15 min) | Matchup defensive rating |
| Team stat categories | `GET /teamstatleaders/nba/seasons` | Startup (cache permanently) | Discover statId mappings |
| Stat trackers | `GET /stattrackers?day={date}&sport=nba` | Pre-game | Prop lines + player discovery |
| Schedule | `GET /home/nba/days?type=condensed` | Daily | B2B detection |
| Tonight's games | `GET /home/nba/next?cohort=0` | Pre-game | Game slate discovery |
| Live feed (Socket.io) | `https://web.realsports.io` LiveFeed socket | Real-time | Layer 2 play-by-play |
| Player box score (Socket.io) | `https://web.realsports.io` PlayerBoxScore socket | Real-time | Live stat accumulation |
| Game markets (Socket.io) | `https://web.realsports.io` GameMarkets socket | Real-time | Real price tracking |

**Note**: Real's WebSocket uses Socket.io (not raw WebSocket). Must use a Socket.io client library (`python-socketio`), not a raw `websockets` connection. Connection is made to `https://web.realsports.io` which upgrades to `wss://` internally.

### Kalshi (Execution Venue)

| Data | Endpoint | Frequency | Purpose |
|---|---|---|---|
| Market list | `GET /markets?series_ticker=KXNBA*&status=open` | Pre-game + every 5-10s | Discover markets, get prices, parse player names |
| Market orderbook | `GET /markets/{ticker}/orderbook` | Every 5-10s during games | Best bid/ask for execution |
| Place order | `POST /portfolio/orders` | On signal | Execute trades |
| Cancel order | `DELETE /portfolio/orders/{id}` | On re-price or exit | Order management |
| Positions | `GET /portfolio/positions` | Every 30s | Track open positions |
| Balance | `GET /portfolio/balance` | Every 60s | Available capital |

---

## 11. Failure Modes & Recovery

### WebSocket Disconnection

| Scenario | Detection | Recovery |
|---|---|---|
| Socket.io disconnect | `disconnect` event | Auto-reconnect (Socket.io built-in, 250ms-1s delay). Re-subscribe to rooms. |
| No data for 30+ seconds | Heartbeat watchdog timer | Mark all live data as STALE. Fall back to REST polling at 5s intervals. Do NOT execute new trades on stale data. |
| Reconnect fails 3 times | Reconnect attempt counter | Switch to REST-only mode for remainder of session. Log alert. |

### Kalshi API Failures

| Scenario | Detection | Recovery |
|---|---|---|
| Order rejected (400) | HTTP 400 response | Log reason. Do NOT retry (likely invalid params). |
| Rate limited (429) | HTTP 429 response | Back off 1 second. Reduce polling frequency by 50%. Resume after 10s. |
| Auth failure (401) | HTTP 401 response | Re-sign request with fresh timestamp. If still failing, halt all trading. |
| Network timeout | No response in 5s | Retry once. If second attempt fails, mark Kalshi as DOWN. No new orders. |
| Partial fill | Order status `partial` | Keep remaining order active. Adjust position tracking for filled portion. |

### Kill Switch

If the system enters an unknown or degraded state:
1. Cancel ALL open (unfilled) orders on Kalshi
2. Stop placing new orders
3. Keep existing positions (they'll settle naturally)
4. Log full system state for diagnosis
5. Send alert (log file / stdout — no external notification in v1)

Trigger conditions:
- Daily loss limit hit
- 3+ consecutive order failures
- Both Real WebSocket AND REST polling are down simultaneously
- Position tracking disagrees with Kalshi reported positions by > 2 contracts

---

## 12. Tech Stack

- **Language**: Python 3.11+ (scipy for stats, asyncio for concurrency)
- **Real API client**: httpx (async HTTP) + python-socketio (Socket.io client)
- **Kalshi API client**: httpx + cryptography (RSA-PSS signing)
- **Probability engine**: scipy.stats.norm for CDF calculations
- **Scheduling**: asyncio event loop with timers
- **Storage**: SQLite for trade log, calibration data, daily P&L, player lookup table, statId cache
- **Configuration**: YAML for risk parameters (easy to tune without code changes) — single source of truth for all limits

---

## 13. Success Criteria

- **Win rate**: 58-68% on triggered trades (above break-even after Kalshi fees)
- **Average edge per trade**: $0.12-0.20 gross, $0.08-0.16 net of fees
- **Daily volume**: 8-20 trades on a full NBA slate
- **Monthly ROI target**: 8-15% on deployed capital
- **Max drawdown tolerance**: 20% of bankroll before full model review
- **Calibration accuracy**: Model's predicted probabilities within 5% of actual hit rates over 200+ trades
- **Paper trade first**: Run on Kalshi demo API for minimum 2 weeks (50+ trades) before deploying real capital
