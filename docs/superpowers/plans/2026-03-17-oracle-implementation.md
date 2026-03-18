# Oracle NBA Multi-Book Trading System — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-book NBA trading system that uses Real Sports App data to find edges on Kalshi prediction markets.

**Architecture:** Shared infrastructure layer (API clients, data models, risk ledger, config) with three independent trading books (A: game divergence, B: pregame player props, C: live events). Each book has its own signal generation, execution rules, and risk parameters. asyncio event loop drives concurrency.

**Tech Stack:** Python 3.11+, httpx (async HTTP), python-socketio (Real WebSocket), cryptography (RSA-PSS for Kalshi auth), scipy (statistics), SQLite (storage), PyYAML (config), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-03-17-oracle-trading-strategy-design.md`

---

## File Structure

```
oracle/
├── config.yaml                    # All risk params, thresholds, per-book settings
├── main.py                        # Entry point: daily cycle orchestrator
├── models.py                      # Shared data models (Signal, Position, Game, Player, etc.)
├── config.py                      # Load + validate YAML config
├── db.py                          # SQLite: trade log, player lookup, opportunity log
├── clients/
│   ├── real_rest.py               # Real Sports REST API client (httpx, Hashids auth)
│   ├── real_ws.py                 # Real Sports Socket.io client (live feed)
│   ├── kalshi.py                  # Kalshi REST API client (RSA-PSS auth, orders)
│   └── matching.py                # Player/market matching: Real ↔ Kalshi entity resolution
├── risk/
│   ├── ledger.py                  # Portfolio risk ledger: positions, exposure, P&L
│   ├── limits.py                  # Hard limit checks (per-book, per-game, per-player, daily)
│   └── fees.py                    # Kalshi fee schedule + net edge calculation
├── books/
│   ├── book_a.py                  # Book A: Real-vs-Kalshi game divergence
│   ├── book_b.py                  # Book B: Pregame player props (empirical distribution)
│   └── book_c.py                  # Book C: Live event signals (foul/OT/blowout)
├── execution/
│   ├── executor.py                # Order placement, re-pricing, cancellation
│   └── quote_check.py             # Quote-age, spread, depth filters (Book C)
└── logging_/
    └── trade_logger.py            # Structured JSON logging, opportunity set, slippage

tests/
├── conftest.py                    # Shared fixtures (mock API responses, sample data)
├── test_models.py                 # Data model tests
├── test_config.py                 # Config loading/validation tests
├── test_db.py                     # SQLite operations tests
├── test_real_rest.py              # Real REST client tests (mocked HTTP)
├── test_kalshi.py                 # Kalshi client tests (mocked HTTP, RSA signing)
├── test_matching.py               # Player/market matching tests
├── test_fees.py                   # Fee calculation tests
├── test_limits.py                 # Risk limit enforcement tests
├── test_ledger.py                 # Portfolio ledger tests
├── test_book_a.py                 # Book A signal generation tests
├── test_book_b.py                 # Book B fair value computation tests
├── test_book_c.py                 # Book C event detection tests
├── test_executor.py               # Order execution tests
└── test_quote_check.py            # Quote quality filter tests
```

---

## Chunk 1: Foundation — Models, Config, Database, Fees

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `oracle/__init__.py`
- Create: `tests/__init__.py`
- Create: `requirements.txt`
- Create: `pyproject.toml`

- [ ] **Step 1: Create project structure**

```bash
cd /Users/andeslee/documents/cursor-projects/sportsmarket
mkdir -p oracle/clients oracle/risk oracle/books oracle/execution oracle/logging_
mkdir -p tests
touch oracle/__init__.py oracle/clients/__init__.py oracle/risk/__init__.py
touch oracle/books/__init__.py oracle/execution/__init__.py oracle/logging_/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

```
httpx>=0.27
python-socketio[asyncio]>=5.11
cryptography>=42.0
scipy>=1.13
pyyaml>=6.0
hashids>=1.3
pytest>=8.0
pytest-asyncio>=0.23
respx>=0.21
```

- [ ] **Step 3: Create pyproject.toml**

```toml
[project]
name = "oracle"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Install dependencies**

Run: `cd /Users/andeslee/documents/cursor-projects/sportsmarket && pip install -r requirements.txt`
Expected: All packages install successfully.

- [ ] **Step 5: Commit**

```bash
git add oracle/ tests/ requirements.txt pyproject.toml
git commit -m "feat: scaffold project structure and dependencies"
```

---

### Task 2: Data models

**Files:**
- Create: `oracle/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for core data models**

```python
# tests/test_models.py
from oracle.models import (
    Book, Signal, Position, Game, Market, Player, PlayerSplits,
    StatTracker, GameState, QuoteSnapshot,
)

def test_signal_creation():
    s = Signal(
        book=Book.A,
        ticker="KXNBAGAME-26MAR18LALHOU-LAL",
        side="yes",
        edge=0.15,
        model_prob=0.72,
        kalshi_price=0.57,
    )
    assert s.book == Book.A
    assert s.edge == 0.15
    assert s.side == "yes"

def test_signal_rejects_negative_edge():
    import pytest
    with pytest.raises(ValueError):
        Signal(book=Book.B, ticker="X", side="yes", edge=-0.05,
               model_prob=0.5, kalshi_price=0.55)

def test_position_cost():
    p = Position(
        book=Book.B,
        ticker="KXNBAPTS-26MAR18-LALLEBRONJ-27",
        side="yes",
        contracts=10,
        fill_price=0.63,
    )
    assert p.cost == 6.30  # 10 * 0.63

def test_game_state_classification():
    assert GameState.classify(margin=5, period="Q3", clock_seconds=300) == GameState.COMPETITIVE
    assert GameState.classify(margin=20, period="Q3", clock_seconds=300) == GameState.BLOWOUT
    assert GameState.classify(margin=3, period="Q4", clock_seconds=120) == GameState.CLUTCH
    assert GameState.classify(margin=0, period="Q4", clock_seconds=90) == GameState.OT_LIKELY

def test_player_splits_hit_rate():
    splits = PlayerSplits(
        last_5=[28, 32, 22, 35, 30],
        last_10=[28, 32, 22, 35, 30, 24, 19, 31, 27, 26],
        season_avg=26.5,
        home_avg=28.0,
        away_avg=25.0,
    )
    assert splits.hit_rate(line=27.5, n=5) == 0.6  # 3 of 5 cleared
    assert splits.hit_rate(line=27.5, n=10) == 0.5  # 5 of 10 cleared
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/andeslee/documents/cursor-projects/sportsmarket && python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'oracle.models'`

- [ ] **Step 3: Implement models**

```python
# oracle/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class Book(Enum):
    A = "game_divergence"
    B = "pregame_props"
    C = "live_events"


class GameState(Enum):
    COMPETITIVE = "competitive"
    BLOWOUT = "blowout"
    CLUTCH = "clutch"
    OT_LIKELY = "ot_likely"
    OVERTIME = "overtime"
    PREGAME = "pregame"
    HALFTIME = "halftime"
    FINAL = "final"

    @classmethod
    def classify(cls, margin: int, period: str, clock_seconds: int) -> GameState:
        abs_margin = abs(margin)
        is_q4 = period == "Q4"
        is_q3_or_later = period in ("Q3", "Q4")

        if is_q4 and clock_seconds <= 120 and abs_margin <= 2:
            return cls.OT_LIKELY
        if is_q4 and clock_seconds <= 300 and abs_margin <= 6:
            return cls.CLUTCH
        if is_q3_or_later and abs_margin >= 20:
            return cls.BLOWOUT
        return cls.COMPETITIVE


@dataclass
class Signal:
    book: Book
    ticker: str
    side: str  # "yes" or "no"
    edge: float
    model_prob: float
    kalshi_price: float
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.edge < 0:
            raise ValueError(f"Edge must be non-negative, got {self.edge}")
        if self.side not in ("yes", "no"):
            raise ValueError(f"Side must be 'yes' or 'no', got {self.side}")


@dataclass
class Position:
    book: Book
    ticker: str
    side: str
    contracts: int
    fill_price: float
    signal_timestamp: float = field(default_factory=time.time)
    fill_timestamp: float = field(default_factory=time.time)
    game_id: Optional[str] = None
    player_id: Optional[int] = None

    @property
    def cost(self) -> float:
        return round(self.contracts * self.fill_price, 2)


@dataclass
class Game:
    game_id: int
    sport: str
    home_team: str
    away_team: str
    status: str  # "scheduled", "live", "final"
    home_score: int = 0
    away_score: int = 0
    period: str = ""
    clock: str = ""
    real_volume: int = 0


@dataclass
class Market:
    ticker: str
    series_ticker: str
    title: str
    yes_price: int  # cents (1-99)
    no_price: int
    volume: int = 0
    yes_bid: int = 0
    yes_ask: int = 0
    status: str = "open"


@dataclass
class Player:
    player_id: int
    name: str
    team: str
    status: str = "Active"  # Active, Out, Questionable
    minutes_avg_last5: float = 0.0
    season_per_minute: dict = field(default_factory=dict)  # {stat: rate}


@dataclass
class PlayerSplits:
    last_5: list[float]
    last_10: list[float]
    season_avg: float
    home_avg: float
    away_avg: float
    per_opponent: dict = field(default_factory=dict)  # {team: avg}

    def hit_rate(self, line: float, n: int = 5) -> float:
        values = self.last_5 if n <= 5 else self.last_10[:n]
        if not values:
            return 0.0
        return sum(1 for v in values if v > line) / len(values)


@dataclass
class StatTracker:
    player_name: str
    stat_type: str
    line: float
    over_odds: Optional[float] = None
    under_odds: Optional[float] = None


@dataclass
class QuoteSnapshot:
    ticker: str
    yes_bid: int
    yes_ask: int
    bid_depth: int  # contracts at best bid
    ask_depth: int  # contracts at best ask
    timestamp: float = field(default_factory=time.time)

    @property
    def spread(self) -> int:
        return self.yes_ask - self.yes_bid

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/models.py tests/test_models.py
git commit -m "feat: add core data models (Signal, Position, Game, Player, etc.)"
```

---

### Task 3: Configuration

**Files:**
- Create: `oracle/config.py`
- Create: `config.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
from oracle.config import load_config, OracleConfig

def test_load_config(tmp_path):
    yaml_content = """
bankroll: 2000
books:
  a:
    enabled: true
    min_edge: 0.15
    position_pct: 0.02
    max_positions: 4
    max_exposure_pct: 0.08
    min_real_volume: 200000
    poll_interval_s: 30
  b:
    enabled: true
    min_edge: 0.10
    position_pct: 0.015
    max_positions: 6
    max_exposure_pct: 0.09
    max_per_game_pct: 0.04
    max_per_player_pct: 0.025
    no_trade_window_min: 15
    min_minutes_avg: 20
  c:
    enabled: true
    min_edge: 0.12
    position_pct: 0.01
    max_positions: 3
    max_exposure_pct: 0.03
    max_slippage_avg: 0.03
    quote_max_age_s: 5
    quote_max_spread: 8
    quote_min_depth: 5
risk:
  max_total_exposure_pct: 0.18
  max_simultaneous_positions: 10
  daily_stop_loss_pct: 0.05
  max_drawdown_pct: 0.15
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_content)

    cfg = load_config(str(config_file))
    assert cfg.bankroll == 2000
    assert cfg.books.a.min_edge == 0.15
    assert cfg.books.b.max_per_player_pct == 0.025
    assert cfg.books.c.quote_max_spread == 8
    assert cfg.risk.max_total_exposure_pct == 0.18

def test_config_dollar_limits():
    from oracle.config import BookAConfig, RiskConfig
    book_a = BookAConfig(
        enabled=True, min_edge=0.15, position_pct=0.02,
        max_positions=4, max_exposure_pct=0.08,
        min_real_volume=200000, poll_interval_s=30,
    )
    assert book_a.max_position_dollars(bankroll=2000) == 40.0  # 2% of 2000
    assert book_a.max_exposure_dollars(bankroll=2000) == 160.0  # 8% of 2000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config loading**

```python
# oracle/config.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import yaml


@dataclass
class BookAConfig:
    enabled: bool
    min_edge: float
    position_pct: float
    max_positions: int
    max_exposure_pct: float
    min_real_volume: int
    poll_interval_s: int

    def max_position_dollars(self, bankroll: float) -> float:
        return bankroll * self.position_pct

    def max_exposure_dollars(self, bankroll: float) -> float:
        return bankroll * self.max_exposure_pct


@dataclass
class BookBConfig:
    enabled: bool
    min_edge: float
    position_pct: float
    max_positions: int
    max_exposure_pct: float
    max_per_game_pct: float
    max_per_player_pct: float
    no_trade_window_min: int
    min_minutes_avg: float

    def max_position_dollars(self, bankroll: float) -> float:
        return bankroll * self.position_pct

    def max_exposure_dollars(self, bankroll: float) -> float:
        return bankroll * self.max_exposure_pct


@dataclass
class BookCConfig:
    enabled: bool
    min_edge: float
    position_pct: float
    max_positions: int
    max_exposure_pct: float
    max_slippage_avg: float
    quote_max_age_s: float
    quote_max_spread: int
    quote_min_depth: int

    def max_position_dollars(self, bankroll: float) -> float:
        return bankroll * self.position_pct

    def max_exposure_dollars(self, bankroll: float) -> float:
        return bankroll * self.max_exposure_pct


@dataclass
class BooksConfig:
    a: BookAConfig
    b: BookBConfig
    c: BookCConfig


@dataclass
class RiskConfig:
    max_total_exposure_pct: float
    max_simultaneous_positions: int
    daily_stop_loss_pct: float
    max_drawdown_pct: float

    def daily_stop_loss_dollars(self, bankroll: float) -> float:
        return bankroll * self.daily_stop_loss_pct


@dataclass
class OracleConfig:
    bankroll: float
    books: BooksConfig
    risk: RiskConfig


def load_config(path: str) -> OracleConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    books = BooksConfig(
        a=BookAConfig(**raw["books"]["a"]),
        b=BookBConfig(**raw["books"]["b"]),
        c=BookCConfig(**raw["books"]["c"]),
    )
    risk = RiskConfig(**raw["risk"])
    return OracleConfig(bankroll=raw["bankroll"], books=books, risk=risk)
```

- [ ] **Step 4: Create the production config.yaml**

```yaml
# config.yaml — Oracle NBA Trading System
# All dollar limits computed dynamically: limit = pct * bankroll

bankroll: 2000

books:
  a:
    enabled: true
    min_edge: 0.15
    position_pct: 0.02
    max_positions: 4
    max_exposure_pct: 0.08
    min_real_volume: 200000
    poll_interval_s: 30
  b:
    enabled: true
    min_edge: 0.10
    position_pct: 0.015
    max_positions: 6
    max_exposure_pct: 0.09
    max_per_game_pct: 0.04
    max_per_player_pct: 0.025
    no_trade_window_min: 15
    min_minutes_avg: 20
  c:
    enabled: true
    min_edge: 0.12
    position_pct: 0.01
    max_positions: 3
    max_exposure_pct: 0.03
    max_slippage_avg: 0.03
    quote_max_age_s: 5
    quote_max_spread: 8
    quote_min_depth: 5

risk:
  max_total_exposure_pct: 0.18
  max_simultaneous_positions: 10
  daily_stop_loss_pct: 0.05
  max_drawdown_pct: 0.15
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add oracle/config.py config.yaml tests/test_config.py
git commit -m "feat: add YAML config loading with per-book risk parameters"
```

---

### Task 4: Kalshi fee calculation

**Files:**
- Create: `oracle/risk/fees.py`
- Create: `tests/test_fees.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fees.py
from oracle.risk.fees import settlement_fee, net_edge

def test_settlement_fee_schedule():
    assert settlement_fee(0.05) == 0.01   # $0.01-0.10 bracket
    assert settlement_fee(0.15) == 0.02   # $0.11-0.20
    assert settlement_fee(0.25) == 0.03   # $0.21-0.30
    assert settlement_fee(0.35) == 0.04   # $0.31-0.40
    assert settlement_fee(0.45) == 0.05   # $0.41-0.50
    assert settlement_fee(0.55) == 0.06   # $0.51-0.60
    assert settlement_fee(0.65) == 0.07   # $0.61-0.99
    assert settlement_fee(0.95) == 0.07

def test_net_edge_calculation():
    # model_prob=0.73, kalshi_price=0.60, buying YES
    # win payout = 1.0 - 0.60 = 0.40, fee on that = $0.04
    # gross edge = 0.73 - 0.60 = 0.13
    # expected fee = 0.73 * 0.04 = 0.029
    # net edge = 0.13 - 0.029 = 0.101
    result = net_edge(model_prob=0.73, kalshi_price=0.60, side="yes")
    assert abs(result - 0.101) < 0.001

def test_net_edge_no_side():
    # Buying NO at 0.40 (kalshi_price for YES = 0.60)
    # model says NO is worth 0.55. kalshi NO = 0.40.
    # win payout = 0.60, fee = $0.06
    # gross edge = 0.55 - 0.40 = 0.15
    # expected fee = 0.55 * 0.06 = 0.033
    result = net_edge(model_prob=0.55, kalshi_price=0.40, side="no")
    assert abs(result - 0.117) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fees.py -v`
Expected: FAIL

- [ ] **Step 3: Implement fee calculation**

```python
# oracle/risk/fees.py
"""Kalshi fee schedule and net edge computation."""

# Fee brackets: (max_settlement_price, fee)
_FEE_SCHEDULE = [
    (0.10, 0.01),
    (0.20, 0.02),
    (0.30, 0.03),
    (0.40, 0.04),
    (0.50, 0.05),
    (0.60, 0.06),
    (0.99, 0.07),
]


def settlement_fee(settlement_price: float) -> float:
    """Return the per-contract fee for a winning settlement at this price."""
    for max_price, fee in _FEE_SCHEDULE:
        if settlement_price <= max_price:
            return fee
    return 0.07


def net_edge(model_prob: float, kalshi_price: float, side: str) -> float:
    """Compute net edge after expected Kalshi fees.

    Args:
        model_prob: Our model's probability for this side (0-1).
        kalshi_price: The price we'd pay on Kalshi (0-1, decimal).
        side: 'yes' or 'no'.

    Returns:
        Net edge in dollars (decimal). Positive = profitable.
    """
    if side == "yes":
        win_settlement = 1.0 - kalshi_price
    else:
        win_settlement = kalshi_price

    fee = settlement_fee(win_settlement)
    gross = model_prob - kalshi_price
    expected_fee = model_prob * fee
    return round(gross - expected_fee, 4)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_fees.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/risk/fees.py tests/test_fees.py
git commit -m "feat: add Kalshi fee schedule and net edge calculation"
```

---

### Task 5: SQLite database layer

**Files:**
- Create: `oracle/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
import sqlite3
from oracle.db import OracleDB

def test_init_creates_tables(tmp_path):
    db = OracleDB(str(tmp_path / "test.db"))
    # Verify tables exist
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {t[0] for t in tables}
    assert "trades" in table_names
    assert "player_lookup" in table_names
    assert "opportunity_log" in table_names
    assert "daily_pnl" in table_names
    conn.close()
    db.close()

def test_player_lookup(tmp_path):
    db = OracleDB(str(tmp_path / "test.db"))
    db.upsert_player("LeBron James", "LAL", 12345)
    assert db.get_player_id("LeBron James", "LAL") == 12345
    assert db.get_player_id("Unknown Player", "BOS") is None
    db.close()

def test_log_trade(tmp_path):
    db = OracleDB(str(tmp_path / "test.db"))
    db.log_trade(
        book="B", ticker="KXNBAPTS-X", side="yes",
        contracts=10, fill_price=0.63, model_prob=0.73,
        edge=0.10, signal_ts=1000.0, fill_ts=1001.0,
    )
    trades = db.get_trades(book="B")
    assert len(trades) == 1
    assert trades[0]["ticker"] == "KXNBAPTS-X"
    db.close()

def test_log_opportunity(tmp_path):
    db = OracleDB(str(tmp_path / "test.db"))
    db.log_opportunity(
        book="B", ticker="KXNBAPTS-X", model_prob=0.73,
        kalshi_price=0.60, edge=0.13, triggered=True, reason="edge>threshold",
    )
    db.log_opportunity(
        book="B", ticker="KXNBAPTS-Y", model_prob=0.55,
        kalshi_price=0.50, edge=0.05, triggered=False, reason="edge<threshold",
    )
    opps = db.get_opportunities(book="B")
    assert len(opps) == 2
    assert opps[0]["triggered"] == 1
    assert opps[1]["triggered"] == 0
    db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL

- [ ] **Step 3: Implement database layer**

```python
# oracle/db.py
"""SQLite persistence for trades, player lookup, and opportunity logging."""
from __future__ import annotations
import sqlite3
from typing import Optional


class OracleDB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book TEXT NOT NULL,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                fill_price REAL NOT NULL,
                model_prob REAL NOT NULL,
                edge REAL NOT NULL,
                signal_ts REAL NOT NULL,
                fill_ts REAL NOT NULL,
                settled INTEGER DEFAULT 0,
                outcome REAL DEFAULT NULL,
                pnl REAL DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS player_lookup (
                name TEXT NOT NULL,
                team TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                PRIMARY KEY (name, team)
            );
            CREATE TABLE IF NOT EXISTS opportunity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book TEXT NOT NULL,
                ticker TEXT NOT NULL,
                model_prob REAL NOT NULL,
                kalshi_price REAL NOT NULL,
                edge REAL NOT NULL,
                triggered INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS daily_pnl (
                date TEXT NOT NULL,
                book TEXT NOT NULL,
                gross_pnl REAL NOT NULL,
                fees REAL NOT NULL,
                net_pnl REAL NOT NULL,
                trades_count INTEGER NOT NULL,
                win_count INTEGER NOT NULL,
                PRIMARY KEY (date, book)
            );
        """)
        self._conn.commit()

    def upsert_player(self, name: str, team: str, player_id: int):
        self._conn.execute(
            "INSERT OR REPLACE INTO player_lookup (name, team, player_id) VALUES (?, ?, ?)",
            (name, team, player_id),
        )
        self._conn.commit()

    def get_player_id(self, name: str, team: str) -> Optional[int]:
        row = self._conn.execute(
            "SELECT player_id FROM player_lookup WHERE name = ? AND team = ?",
            (name, team),
        ).fetchone()
        return row["player_id"] if row else None

    def log_trade(self, *, book: str, ticker: str, side: str, contracts: int,
                  fill_price: float, model_prob: float, edge: float,
                  signal_ts: float, fill_ts: float):
        self._conn.execute(
            """INSERT INTO trades (book, ticker, side, contracts, fill_price,
               model_prob, edge, signal_ts, fill_ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (book, ticker, side, contracts, fill_price, model_prob, edge,
             signal_ts, fill_ts),
        )
        self._conn.commit()

    def get_trades(self, book: Optional[str] = None) -> list[dict]:
        if book:
            rows = self._conn.execute(
                "SELECT * FROM trades WHERE book = ? ORDER BY id", (book,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def log_opportunity(self, *, book: str, ticker: str, model_prob: float,
                        kalshi_price: float, edge: float, triggered: bool,
                        reason: str = ""):
        self._conn.execute(
            """INSERT INTO opportunity_log (book, ticker, model_prob, kalshi_price,
               edge, triggered, reason) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (book, ticker, model_prob, kalshi_price, edge, int(triggered), reason),
        )
        self._conn.commit()

    def get_opportunities(self, book: Optional[str] = None) -> list[dict]:
        if book:
            rows = self._conn.execute(
                "SELECT * FROM opportunity_log WHERE book = ? ORDER BY id", (book,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM opportunity_log ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/db.py tests/test_db.py
git commit -m "feat: add SQLite layer for trades, player lookup, and opportunity log"
```

---

### Task 6: Risk ledger and limit checks

**Files:**
- Create: `oracle/risk/ledger.py`
- Create: `oracle/risk/limits.py`
- Create: `tests/test_ledger.py`
- Create: `tests/test_limits.py`

- [ ] **Step 1: Write failing tests for ledger**

```python
# tests/test_ledger.py
from oracle.risk.ledger import RiskLedger
from oracle.models import Book, Position

def test_add_position_tracks_exposure():
    ledger = RiskLedger()
    pos = Position(book=Book.B, ticker="X", side="yes",
                   contracts=10, fill_price=0.63, game_id="G1", player_id=100)
    ledger.add(pos)
    assert ledger.total_exposure() == 6.30
    assert ledger.book_exposure(Book.B) == 6.30
    assert ledger.game_exposure("G1") == 6.30
    assert ledger.player_exposure(100) == 6.30
    assert ledger.position_count() == 1

def test_settle_position():
    ledger = RiskLedger()
    pos = Position(book=Book.B, ticker="X", side="yes",
                   contracts=10, fill_price=0.63, game_id="G1")
    ledger.add(pos)
    pnl = ledger.settle("X", won=True, fee_per_contract=0.04)
    # Won: (1.0 - 0.63 - 0.04) * 10 = 0.33 * 10 = 3.30
    assert abs(pnl - 3.30) < 0.01
    assert ledger.total_exposure() == 0.0
    assert ledger.daily_pnl == 3.30

def test_settle_loss():
    ledger = RiskLedger()
    pos = Position(book=Book.B, ticker="X", side="yes",
                   contracts=10, fill_price=0.63)
    ledger.add(pos)
    pnl = ledger.settle("X", won=False, fee_per_contract=0.0)
    assert abs(pnl - (-6.30)) < 0.01
    assert ledger.daily_pnl == -6.30
```

- [ ] **Step 2: Write failing tests for limits**

```python
# tests/test_limits.py
from oracle.risk.limits import check_limits
from oracle.risk.ledger import RiskLedger
from oracle.models import Book, Signal, Position
from oracle.config import (
    OracleConfig, BooksConfig, BookAConfig, BookBConfig,
    BookCConfig, RiskConfig,
)

def _test_config():
    return OracleConfig(
        bankroll=2000,
        books=BooksConfig(
            a=BookAConfig(enabled=True, min_edge=0.15, position_pct=0.02,
                          max_positions=4, max_exposure_pct=0.08,
                          min_real_volume=200000, poll_interval_s=30),
            b=BookBConfig(enabled=True, min_edge=0.10, position_pct=0.015,
                          max_positions=6, max_exposure_pct=0.09,
                          max_per_game_pct=0.04, max_per_player_pct=0.025,
                          no_trade_window_min=15, min_minutes_avg=20),
            c=BookCConfig(enabled=True, min_edge=0.12, position_pct=0.01,
                          max_positions=3, max_exposure_pct=0.03,
                          max_slippage_avg=0.03, quote_max_age_s=5,
                          quote_max_spread=8, quote_min_depth=5),
        ),
        risk=RiskConfig(max_total_exposure_pct=0.18,
                        max_simultaneous_positions=10,
                        daily_stop_loss_pct=0.05, max_drawdown_pct=0.15),
    )

def test_allows_valid_trade():
    cfg = _test_config()
    ledger = RiskLedger()
    signal = Signal(book=Book.B, ticker="X", side="yes",
                    edge=0.12, model_prob=0.72, kalshi_price=0.60)
    result = check_limits(cfg, ledger, signal, game_id="G1", player_id=100)
    assert result.allowed is True

def test_blocks_daily_stop_loss():
    cfg = _test_config()
    ledger = RiskLedger()
    ledger.daily_pnl = -100.0  # -$100 = -5% of $2000
    signal = Signal(book=Book.B, ticker="X", side="yes",
                    edge=0.12, model_prob=0.72, kalshi_price=0.60)
    result = check_limits(cfg, ledger, signal, game_id="G1")
    assert result.allowed is False
    assert "daily_stop_loss" in result.reason

def test_blocks_max_positions():
    cfg = _test_config()
    ledger = RiskLedger()
    for i in range(10):
        ledger.add(Position(book=Book.B, ticker=f"T{i}", side="yes",
                            contracts=1, fill_price=0.10))
    signal = Signal(book=Book.B, ticker="NEW", side="yes",
                    edge=0.12, model_prob=0.72, kalshi_price=0.60)
    result = check_limits(cfg, ledger, signal)
    assert result.allowed is False
    assert "max_simultaneous" in result.reason

def test_blocks_per_player_exposure():
    cfg = _test_config()
    ledger = RiskLedger()
    # Add $50 exposure to player 100 (2.5% of $2000 = $50 limit)
    ledger.add(Position(book=Book.B, ticker="T1", side="yes",
                        contracts=100, fill_price=0.50, player_id=100))
    signal = Signal(book=Book.B, ticker="T2", side="yes",
                    edge=0.12, model_prob=0.72, kalshi_price=0.60)
    result = check_limits(cfg, ledger, signal, player_id=100)
    assert result.allowed is False
    assert "per_player" in result.reason
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_ledger.py tests/test_limits.py -v`
Expected: FAIL

- [ ] **Step 4: Implement ledger**

```python
# oracle/risk/ledger.py
from __future__ import annotations
from oracle.models import Book, Position


class RiskLedger:
    def __init__(self):
        self._positions: dict[str, Position] = {}  # ticker -> Position
        self.daily_pnl: float = 0.0

    def add(self, position: Position):
        self._positions[position.ticker] = position

    def remove(self, ticker: str) -> Position | None:
        return self._positions.pop(ticker, None)

    def settle(self, ticker: str, won: bool, fee_per_contract: float = 0.0) -> float:
        pos = self._positions.pop(ticker, None)
        if pos is None:
            return 0.0
        if won:
            payout_per = (1.0 - pos.fill_price) - fee_per_contract
            pnl = round(payout_per * pos.contracts, 2)
        else:
            pnl = round(-pos.cost, 2)
        self.daily_pnl = round(self.daily_pnl + pnl, 2)
        return pnl

    def total_exposure(self) -> float:
        return round(sum(p.cost for p in self._positions.values()), 2)

    def book_exposure(self, book: Book) -> float:
        return round(sum(p.cost for p in self._positions.values() if p.book == book), 2)

    def book_position_count(self, book: Book) -> int:
        return sum(1 for p in self._positions.values() if p.book == book)

    def game_exposure(self, game_id: str) -> float:
        return round(sum(p.cost for p in self._positions.values()
                         if p.game_id == game_id), 2)

    def player_exposure(self, player_id: int) -> float:
        return round(sum(p.cost for p in self._positions.values()
                         if p.player_id == player_id), 2)

    def position_count(self) -> int:
        return len(self._positions)

    def get_position(self, ticker: str) -> Position | None:
        return self._positions.get(ticker)

    def all_positions(self) -> list[Position]:
        return list(self._positions.values())
```

- [ ] **Step 5: Implement limits**

```python
# oracle/risk/limits.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from oracle.models import Book, Signal
from oracle.risk.ledger import RiskLedger
from oracle.config import OracleConfig


@dataclass
class LimitResult:
    allowed: bool
    reason: str = ""


def check_limits(
    cfg: OracleConfig,
    ledger: RiskLedger,
    signal: Signal,
    game_id: Optional[str] = None,
    player_id: Optional[int] = None,
) -> LimitResult:
    bankroll = cfg.bankroll

    # Daily stop-loss
    if ledger.daily_pnl <= -cfg.risk.daily_stop_loss_pct * bankroll:
        return LimitResult(False, "daily_stop_loss")

    # Max simultaneous positions
    if ledger.position_count() >= cfg.risk.max_simultaneous_positions:
        return LimitResult(False, "max_simultaneous")

    # Max total exposure
    if ledger.total_exposure() >= cfg.risk.max_total_exposure_pct * bankroll:
        return LimitResult(False, "max_total_exposure")

    # Per-book limits
    book_cfg = _get_book_config(cfg, signal.book)
    if not book_cfg.enabled:
        return LimitResult(False, "book_disabled")

    if ledger.book_position_count(signal.book) >= book_cfg.max_positions:
        return LimitResult(False, "book_max_positions")

    if ledger.book_exposure(signal.book) >= book_cfg.max_exposure_dollars(bankroll):
        return LimitResult(False, "book_max_exposure")

    # Per-game exposure (Book B)
    if signal.book == Book.B and game_id:
        max_game = cfg.books.b.max_per_game_pct * bankroll
        if ledger.game_exposure(game_id) >= max_game:
            return LimitResult(False, "per_game_exposure")

    # Per-player exposure (Book B)
    if signal.book == Book.B and player_id:
        max_player = cfg.books.b.max_per_player_pct * bankroll
        if ledger.player_exposure(player_id) >= max_player:
            return LimitResult(False, "per_player_exposure")

    return LimitResult(True)


def _get_book_config(cfg: OracleConfig, book: Book):
    if book == Book.A:
        return cfg.books.a
    elif book == Book.B:
        return cfg.books.b
    else:
        return cfg.books.c
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_ledger.py tests/test_limits.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add oracle/risk/ledger.py oracle/risk/limits.py tests/test_ledger.py tests/test_limits.py
git commit -m "feat: add risk ledger and limit enforcement engine"
```

---

## Chunk 2: API Clients — Real Sports + Kalshi

### Task 7: Real Sports REST client

**Files:**
- Create: `oracle/clients/real_rest.py`
- Create: `tests/test_real_rest.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/conftest.py
import pytest

@pytest.fixture
def real_auth():
    return {
        "user_id": "testuser",
        "device_id": "testdevice",
        "token": "testtoken-uuid",
        "device_uuid": "test-uuid",
    }
```

```python
# tests/test_real_rest.py
import pytest
import respx
import httpx
from oracle.clients.real_rest import RealClient

BASE = "https://web.realapp.com"

@pytest.fixture
def client(real_auth):
    return RealClient(**real_auth)

@respx.mock
@pytest.mark.asyncio
async def test_get_game_markets(client):
    respx.get(f"{BASE}/predictions/gamemarkets/nba").mock(
        return_value=httpx.Response(200, json={
            "markets": [{"marketId": 1, "outcomes": [
                {"name": "LAL", "probability": 68},
                {"name": "HOU", "probability": 32},
            ], "volume": 500000}]
        })
    )
    markets = await client.get_game_markets("nba")
    assert len(markets) == 1
    assert markets[0]["volume"] == 500000

@respx.mock
@pytest.mark.asyncio
async def test_get_player_profile(client):
    respx.get(f"{BASE}/players/12345/sport/nba").mock(
        return_value=httpx.Response(200, json={
            "name": "LeBron James",
            "seasonStats": {"pts": 27.1},
            "splits": {"averages": [{"period": "Last 5", "stats": {"pts": 31.2}}]},
        })
    )
    profile = await client.get_player_profile(12345, "nba", season=2025)
    assert profile["name"] == "LeBron James"

@respx.mock
@pytest.mark.asyncio
async def test_get_stat_trackers(client):
    respx.get(f"{BASE}/stattrackers").mock(
        return_value=httpx.Response(200, json={
            "trackers": [{"playerName": "LeBron James",
                          "statType": "points", "line": 27.5,
                          "overOdds": -130, "underOdds": 110}]
        })
    )
    trackers = await client.get_stat_trackers("2026-03-18", "nba")
    assert trackers[0]["overOdds"] == -130

@respx.mock
@pytest.mark.asyncio
async def test_request_token_header(client):
    route = respx.get(f"{BASE}/home/nba/next").mock(
        return_value=httpx.Response(200, json={})
    )
    await client.get_tonight_games("nba")
    request = route.calls[0].request
    assert "real-request-token" in request.headers
    assert len(request.headers["real-request-token"]) == 16
    assert request.headers["real-version"] == "28"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_real_rest.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Real REST client**

```python
# oracle/clients/real_rest.py
"""Real Sports App REST API client with Hashids auth."""
from __future__ import annotations
import time
import httpx
from hashids import Hashids

BASE_URL = "https://web.realapp.com"
_hashids = Hashids("realwebapp", 16)


class RealClient:
    def __init__(self, user_id: str, device_id: str, token: str, device_uuid: str):
        self._auth_info = f"{user_id}!{device_id}!{token}"
        self._device_uuid = device_uuid
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)

    def _headers(self) -> dict:
        return {
            "real-auth-info": self._auth_info,
            "real-device-type": "desktop_web",
            "real-device-uuid": self._device_uuid,
            "real-request-token": _hashids.encode(int(time.time() * 1000)),
            "real-version": "28",
            "accept": "application/json",
            "content-type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._http.get(path, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_game_markets(self, sport: str = "nba") -> list[dict]:
        data = await self._get(f"/predictions/gamemarkets/{sport}")
        return data.get("markets", data if isinstance(data, list) else [])

    async def get_player_profile(self, player_id: int, sport: str = "nba",
                                  season: int = 2025) -> dict:
        return await self._get(
            f"/players/{player_id}/sport/{sport}",
            params={"season": str(season)},
        )

    async def get_player_season_feed(self, player_id: int, sport: str = "nba",
                                      limit: int = 20, season: int = 2025) -> dict:
        return await self._get(
            f"/players/{player_id}/sport/{sport}/seasonfeed",
            params={"limit": str(limit), "season": str(season),
                    "view": "recent", "viewFrame": "default"},
        )

    async def get_stat_trackers(self, day: str, sport: str = "nba") -> list[dict]:
        data = await self._get("/stattrackers", params={"day": day, "sport": sport})
        return data.get("trackers", data if isinstance(data, list) else [])

    async def get_tonight_games(self, sport: str = "nba") -> dict:
        return await self._get(f"/home/{sport}/next", params={"cohort": "0"})

    async def get_schedule(self, sport: str = "nba") -> dict:
        return await self._get(f"/home/{sport}/days", params={"type": "condensed"})

    async def get_team_stat_seasons(self, sport: str = "nba") -> dict:
        return await self._get(f"/teamstatleaders/{sport}/seasons")

    async def get_team_stat_leaders(self, sport: str, year: int,
                                     stat_id: int) -> dict:
        return await self._get(
            f"/teamstatleaders/{sport}/seasons/{year}/seasontypes/regularseason/stats/{stat_id}"
        )

    async def get_team_standings(self, sport: str, conference: str,
                                  division: str, season: int = 2025) -> dict:
        return await self._get(
            f"/teamstandings/sport/{sport}/conference/{conference}/division/{division}",
            params={"season": str(season)},
        )

    async def get_team_rankings(self, sport: str, period: str) -> dict:
        return await self._get(
            f"/rankings/sport/{sport}/entity/team/ranking/{period}"
        )

    async def get_player_rankings(self, sport: str, period: str) -> dict:
        return await self._get(
            f"/rankings/sport/{sport}/entity/player/ranking/{period}"
        )

    async def search_players(self, sport: str = "nba", season: int = 2025) -> dict:
        return await self._get(
            f"/players/sport/{sport}/search",
            params={"includeNoOneOption": "false", "searchType": "cardsTabUpsell",
                    "season": str(season)},
        )

    async def close(self):
        await self._http.aclose()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_real_rest.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/clients/real_rest.py tests/test_real_rest.py tests/conftest.py
git commit -m "feat: add Real Sports REST client with Hashids auth"
```

---

### Task 8: Kalshi REST client with RSA-PSS auth

**Files:**
- Create: `oracle/clients/kalshi.py`
- Create: `tests/test_kalshi.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_kalshi.py
import pytest
import respx
import httpx
from unittest.mock import patch
from oracle.clients.kalshi import KalshiClient

DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"

@pytest.fixture
def kalshi_client(tmp_path):
    # Generate a test RSA key pair
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return KalshiClient(
        key_id="test-key-id",
        private_key_path=str(key_path),
        base_url=DEMO_BASE,
    )

@respx.mock
@pytest.mark.asyncio
async def test_get_markets(kalshi_client):
    respx.get(f"{DEMO_BASE}/markets").mock(
        return_value=httpx.Response(200, json={
            "markets": [{"ticker": "KXNBAGAME-26MAR18LALHOU-LAL",
                          "yes_price": 49, "no_price": 51, "volume": 1000}],
            "cursor": "",
        })
    )
    markets = await kalshi_client.get_markets(series_ticker="KXNBAGAME", status="open")
    assert len(markets) == 1
    assert markets[0]["yes_price"] == 49

@respx.mock
@pytest.mark.asyncio
async def test_place_order(kalshi_client):
    respx.post(f"{DEMO_BASE}/portfolio/orders").mock(
        return_value=httpx.Response(200, json={
            "order": {"order_id": "abc123", "status": "resting"}
        })
    )
    result = await kalshi_client.place_order(
        ticker="KXNBAGAME-26MAR18LALHOU-LAL",
        action="buy", side="yes", type_="limit",
        count=10, yes_price=49,
    )
    assert result["order"]["order_id"] == "abc123"

@respx.mock
@pytest.mark.asyncio
async def test_auth_headers_present(kalshi_client):
    route = respx.get(f"{DEMO_BASE}/portfolio/balance").mock(
        return_value=httpx.Response(200, json={"balance": 100000})
    )
    await kalshi_client.get_balance()
    request = route.calls[0].request
    assert "KALSHI-ACCESS-KEY" in request.headers
    assert "KALSHI-ACCESS-TIMESTAMP" in request.headers
    assert "KALSHI-ACCESS-SIGNATURE" in request.headers

@respx.mock
@pytest.mark.asyncio
async def test_get_orderbook(kalshi_client):
    ticker = "KXNBAPTS-26MAR18-LALLEBRONJ-27"
    respx.get(f"{DEMO_BASE}/markets/{ticker}/orderbook").mock(
        return_value=httpx.Response(200, json={
            "orderbook": {
                "yes": [[49, 20], [48, 50]],
                "no": [[52, 15], [53, 30]],
            }
        })
    )
    book = await kalshi_client.get_orderbook(ticker)
    assert book["orderbook"]["yes"][0] == [49, 20]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_kalshi.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Kalshi client**

```python
# oracle/clients/kalshi.py
"""Kalshi REST API client with RSA-PSS authentication."""
from __future__ import annotations
import time
import base64
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiClient:
    def __init__(self, key_id: str, private_key_path: str,
                 base_url: str = "https://demo-api.kalshi.co/trade-api/v2"):
        self._key_id = key_id
        self._base_url = base_url
        with open(private_key_path, "rb") as f:
            self._private_key = serialization.load_pem_private_key(
                f.read(), password=None,
            )
        self._http = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    def _sign(self, method: str, path: str) -> dict:
        timestamp = str(int(time.time() * 1000))
        path_no_query = path.split("?")[0]
        message = f"{timestamp}{method}{path_no_query}".encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        headers = self._sign("GET", path)
        resp = await self._http.get(path, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json_body: dict) -> dict:
        headers = self._sign("POST", path)
        resp = await self._http.post(path, headers=headers, json=json_body)
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str) -> dict:
        headers = self._sign("DELETE", path)
        resp = await self._http.delete(path, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_markets(self, series_ticker: str = "",
                          status: str = "open",
                          limit: int = 200) -> list[dict]:
        params = {"status": status, "limit": str(limit)}
        if series_ticker:
            params["series_ticker"] = series_ticker
        data = await self._get("/markets", params=params)
        return data.get("markets", [])

    async def get_orderbook(self, ticker: str) -> dict:
        return await self._get(f"/markets/{ticker}/orderbook")

    async def place_order(self, ticker: str, action: str, side: str,
                          type_: str, count: int, yes_price: int,
                          time_in_force: str = "good_till_canceled") -> dict:
        body = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "type": type_,
            "count": count,
            "yes_price": yes_price,
            "time_in_force": time_in_force,
        }
        return await self._post("/portfolio/orders", body)

    async def cancel_order(self, order_id: str) -> dict:
        return await self._delete(f"/portfolio/orders/{order_id}")

    async def get_positions(self) -> list[dict]:
        data = await self._get("/portfolio/positions")
        return data.get("market_positions", data if isinstance(data, list) else [])

    async def get_balance(self) -> dict:
        return await self._get("/portfolio/balance")

    async def close(self):
        await self._http.aclose()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_kalshi.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/clients/kalshi.py tests/test_kalshi.py
git commit -m "feat: add Kalshi REST client with RSA-PSS signing"
```

---

### Task 9: Player/market matching

**Files:**
- Create: `oracle/clients/matching.py`
- Create: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_matching.py
from oracle.clients.matching import normalize_name, fuzzy_match_player, parse_kalshi_prop_title

def test_normalize_name():
    assert normalize_name("LeBron James") == "lebron james"
    assert normalize_name("Shai Gilgeous-Alexander") == "shai gilgeous-alexander"
    assert normalize_name("LaMelo Ball Jr.") == "lamelo ball"
    assert normalize_name("Jaren Jackson III") == "jaren jackson"

def test_parse_kalshi_prop_title():
    result = parse_kalshi_prop_title("LeBron James Over 27.5 Points")
    assert result["player_name"] == "LeBron James"
    assert result["line"] == 27.5
    assert result["stat"] == "points"
    assert result["direction"] == "over"

    result2 = parse_kalshi_prop_title("Shai Gilgeous-Alexander Under 6.5 Assists")
    assert result2["player_name"] == "Shai Gilgeous-Alexander"
    assert result2["line"] == 6.5
    assert result2["stat"] == "assists"

def test_fuzzy_match_player():
    real_players = [
        {"name": "LeBron James", "player_id": 100},
        {"name": "LaMelo Ball", "player_id": 200},
        {"name": "Shai Gilgeous-Alexander", "player_id": 300},
    ]
    assert fuzzy_match_player("LeBron James", real_players) == 100
    assert fuzzy_match_player("Lebron James", real_players) == 100  # case insensitive
    assert fuzzy_match_player("Unknown Player", real_players) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_matching.py -v`
Expected: FAIL

- [ ] **Step 3: Implement matching**

```python
# oracle/clients/matching.py
"""Entity resolution: match Real players to Kalshi market tickers."""
from __future__ import annotations
import re
from typing import Optional


_SUFFIXES = re.compile(r"\s+(Jr\.?|Sr\.?|III|II|IV|V)\s*$", re.IGNORECASE)


def normalize_name(name: str) -> str:
    cleaned = _SUFFIXES.sub("", name).strip()
    return cleaned.lower()


def parse_kalshi_prop_title(title: str) -> dict:
    """Parse 'LeBron James Over 27.5 Points' into components."""
    pattern = re.compile(
        r"^(.+?)\s+(Over|Under)\s+([\d.]+)\s+(.+)$", re.IGNORECASE
    )
    m = pattern.match(title)
    if not m:
        return {}
    return {
        "player_name": m.group(1).strip(),
        "line": float(m.group(3)),
        "direction": m.group(2).lower(),
        "stat": m.group(4).strip().lower(),
    }


def fuzzy_match_player(
    kalshi_name: str,
    real_players: list[dict],
) -> Optional[int]:
    """Match a Kalshi player name to a Real player_id.

    Uses normalized exact match first, then falls back to
    checking if one name contains the other.
    """
    target = normalize_name(kalshi_name)

    # Exact normalized match
    for p in real_players:
        if normalize_name(p["name"]) == target:
            return p["player_id"]

    # Containment fallback (for partial name differences)
    for p in real_players:
        real_norm = normalize_name(p["name"])
        if target in real_norm or real_norm in target:
            return p["player_id"]

    return None
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_matching.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/clients/matching.py tests/test_matching.py
git commit -m "feat: add player/market matching with name normalization"
```

---

## Chunk 3: Trading Books A, B, C

### Task 10: Book A — Game divergence

**Files:**
- Create: `oracle/books/book_a.py`
- Create: `tests/test_book_a.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_book_a.py
from oracle.books.book_a import scan_divergence
from oracle.models import Book

def test_detects_positive_edge():
    real_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "home_prob": 68, "volume": 500000},
    ]
    kalshi_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "ticker_yes": "KXNBAGAME-26MAR18LALHOU-LAL",
         "ticker_no": "KXNBAGAME-26MAR18LALHOU-HOU",
         "yes_price": 50},
    ]
    signals = scan_divergence(real_markets, kalshi_markets, min_edge=0.15, min_volume=200000)
    assert len(signals) == 1
    assert signals[0].side == "yes"
    assert abs(signals[0].edge - 0.18) < 0.01  # 0.68 - 0.50

def test_skips_low_volume():
    real_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "home_prob": 68, "volume": 50000},  # below 200k
    ]
    kalshi_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "ticker_yes": "X", "ticker_no": "Y", "yes_price": 50},
    ]
    signals = scan_divergence(real_markets, kalshi_markets, min_edge=0.15, min_volume=200000)
    assert len(signals) == 0

def test_skips_below_threshold():
    real_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "home_prob": 55, "volume": 500000},
    ]
    kalshi_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "ticker_yes": "X", "ticker_no": "Y", "yes_price": 50},
    ]
    signals = scan_divergence(real_markets, kalshi_markets, min_edge=0.15, min_volume=200000)
    assert len(signals) == 0  # 0.55 - 0.50 = 0.05, below 0.15

def test_detects_no_side_edge():
    real_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "home_prob": 40, "volume": 500000},  # Real thinks LAL is worse
    ]
    kalshi_markets = [
        {"game_id": 1, "home": "LAL", "away": "HOU",
         "ticker_yes": "X-LAL", "ticker_no": "X-HOU", "yes_price": 60},
    ]
    signals = scan_divergence(real_markets, kalshi_markets, min_edge=0.15, min_volume=200000)
    assert len(signals) == 1
    assert signals[0].side == "no"
    assert abs(signals[0].edge - 0.20) < 0.01  # |0.40 - 0.60|
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_book_a.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Book A**

```python
# oracle/books/book_a.py
"""Book A: Real-vs-Kalshi game-level price divergence."""
from __future__ import annotations
from oracle.models import Book, Signal


def scan_divergence(
    real_markets: list[dict],
    kalshi_markets: list[dict],
    min_edge: float,
    min_volume: int,
) -> list[Signal]:
    """Compare Real's implied probability to Kalshi's price for matched games."""
    # Index Kalshi by game_id
    kalshi_by_game = {m["game_id"]: m for m in kalshi_markets}

    signals = []
    for rm in real_markets:
        if rm["volume"] < min_volume:
            continue

        km = kalshi_by_game.get(rm["game_id"])
        if not km:
            continue

        real_prob = rm["home_prob"] / 100
        kalshi_price = km["yes_price"] / 100

        edge = real_prob - kalshi_price

        if abs(edge) >= min_edge:
            if edge > 0:
                signals.append(Signal(
                    book=Book.A,
                    ticker=km["ticker_yes"],
                    side="yes",
                    edge=round(abs(edge), 4),
                    model_prob=real_prob,
                    kalshi_price=kalshi_price,
                ))
            else:
                signals.append(Signal(
                    book=Book.A,
                    ticker=km["ticker_no"],
                    side="no",
                    edge=round(abs(edge), 4),
                    model_prob=round(1 - real_prob, 4),
                    kalshi_price=round(1 - kalshi_price, 4),
                ))

    return signals
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_book_a.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/books/book_a.py tests/test_book_a.py
git commit -m "feat: add Book A — Real-vs-Kalshi game divergence scanner"
```

---

### Task 11: Book B — Pregame player props fair value

**Files:**
- Create: `oracle/books/book_b.py`
- Create: `tests/test_book_b.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_book_b.py
from oracle.books.book_b import (
    compute_fair_value, weighted_hit_rate,
    apply_matchup_shift, apply_venue_shift,
    implied_probability, LineupGate, check_lineup_gate,
)

def test_weighted_hit_rate():
    # 20 game values, line 27.5
    values = [30, 25, 32, 28, 35, 22, 31, 27, 29, 26,
              24, 33, 21, 28, 30, 25, 27, 31, 23, 29]
    rate = weighted_hit_rate(values, line=27.5)
    # Last 5: [30, 25, 32, 28, 35] → 3 over (weight 2.0 each = 6.0 hits / 10.0 total)
    # Last 6-10: [22, 31, 27, 29, 26] → 2 over (weight 1.5 each = 3.0 / 7.5 total)
    # Last 11-20: [24, 33, 21, 28, 30, 25, 27, 31, 23, 29] → 4 over (1.0 each)
    # Total hits: 6.0 + 3.0 + 4.0 = 13.0, total weight: 10.0 + 7.5 + 10.0 = 27.5
    assert abs(rate - 13.0/27.5) < 0.01

def test_apply_matchup_shift_bad_defense():
    values = [25, 28, 30, 27, 26]
    shift = apply_matchup_shift(values, opp_def_rank=28, opp_history=None)
    mean_val = sum(values) / len(values)
    assert shift > 0  # Bad defense → positive shift
    assert abs(shift - 0.08 * mean_val) < 0.1

def test_apply_matchup_shift_good_defense():
    values = [25, 28, 30, 27, 26]
    shift = apply_matchup_shift(values, opp_def_rank=3, opp_history=None)
    assert shift < 0  # Good defense → negative shift

def test_apply_matchup_shift_with_opponent_history():
    values = [25, 28, 30, 27, 26]
    opp_history = {"games": 4, "average": 35.0}
    shift = apply_matchup_shift(values, opp_def_rank=15, opp_history=opp_history)
    mean_val = sum(values) / len(values)
    expected = (35.0 - mean_val) * 0.5  # Blend toward opp-specific avg
    assert abs(shift - expected) < 0.1

def test_apply_venue_shift_home():
    assert abs(apply_venue_shift(home_avg=28.0, away_avg=25.0, is_home=True) - 0.9) < 0.1
    # (28 - 25) * 0.3 = 0.9

def test_apply_venue_shift_away():
    assert abs(apply_venue_shift(home_avg=28.0, away_avg=25.0, is_home=False) - (-0.9)) < 0.1

def test_implied_probability():
    assert abs(implied_probability(-130) - 0.5652) < 0.01  # -130 → 56.5%
    assert abs(implied_probability(110) - 0.4762) < 0.01   # +110 → 47.6%
    assert abs(implied_probability(-200) - 0.6667) < 0.01  # -200 → 66.7%

def test_lineup_gate_questionable():
    gate = check_lineup_gate(player_status="Questionable", minutes_avg=32,
                              key_teammate_questionable=False, minutes_to_tip=60)
    assert gate == LineupGate.PLAYER_QUESTIONABLE

def test_lineup_gate_low_minutes():
    gate = check_lineup_gate(player_status="Active", minutes_avg=15,
                              key_teammate_questionable=False, minutes_to_tip=60)
    assert gate == LineupGate.LOW_MINUTES

def test_lineup_gate_no_trade_window():
    gate = check_lineup_gate(player_status="Active", minutes_avg=32,
                              key_teammate_questionable=False, minutes_to_tip=10)
    assert gate == LineupGate.NO_TRADE_WINDOW

def test_lineup_gate_clear():
    gate = check_lineup_gate(player_status="Active", minutes_avg=32,
                              key_teammate_questionable=False, minutes_to_tip=60)
    assert gate == LineupGate.CLEAR
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_book_b.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Book B**

```python
# oracle/books/book_b.py
"""Book B: Pregame NBA player props fair value computation."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from oracle.models import Book, Signal


class LineupGate(Enum):
    CLEAR = "clear"
    PLAYER_QUESTIONABLE = "player_questionable"
    TEAMMATE_QUESTIONABLE = "teammate_questionable"
    NO_TRADE_WINDOW = "no_trade_window"
    LOW_MINUTES = "low_minutes"


def check_lineup_gate(
    player_status: str,
    minutes_avg: float,
    key_teammate_questionable: bool,
    minutes_to_tip: float,
    min_minutes: float = 20,
    no_trade_window: float = 15,
) -> LineupGate:
    if player_status == "Questionable":
        return LineupGate.PLAYER_QUESTIONABLE
    if key_teammate_questionable:
        return LineupGate.TEAMMATE_QUESTIONABLE
    if minutes_to_tip < no_trade_window:
        return LineupGate.NO_TRADE_WINDOW
    if minutes_avg < min_minutes:
        return LineupGate.LOW_MINUTES
    return LineupGate.CLEAR


def implied_probability(american_odds: float) -> float:
    """Convert American odds to implied probability."""
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    else:
        return 100 / (american_odds + 100)


def weighted_hit_rate(values: list[float], line: float) -> float:
    """Compute recency-weighted hit rate.

    Last 5 games: 2.0x weight
    Games 6-10: 1.5x weight
    Games 11+: 1.0x weight
    """
    if not values:
        return 0.0

    total_weight = 0.0
    total_hits = 0.0
    for i, v in enumerate(values):
        if i < 5:
            w = 2.0
        elif i < 10:
            w = 1.5
        else:
            w = 1.0
        total_weight += w
        if v > line:
            total_hits += w

    return total_hits / total_weight if total_weight > 0 else 0.0


def apply_matchup_shift(
    values: list[float],
    opp_def_rank: int,
    opp_history: Optional[dict],
) -> float:
    """Compute matchup-based shift to the distribution."""
    mean_val = sum(values) / len(values) if values else 0
    shift = 0.0

    # Per-opponent history (if enough data)
    if opp_history and opp_history.get("games", 0) >= 3:
        opp_avg = opp_history["average"]
        shift = (opp_avg - mean_val) * 0.5
    else:
        # Opponent defensive ranking
        if opp_def_rank >= 25:
            shift = 0.08 * mean_val
        elif opp_def_rank <= 5:
            shift = -0.08 * mean_val

    return shift


def apply_venue_shift(home_avg: float, away_avg: float, is_home: bool) -> float:
    """Compute venue-based shift."""
    delta = home_avg - away_avg
    if is_home:
        return delta * 0.3
    else:
        return -delta * 0.3


def compute_fair_value(
    game_values: list[float],
    line: float,
    matchup_shift: float = 0.0,
    venue_shift: float = 0.0,
    b2b_penalty_pct: float = 0.0,
    pace_factor: float = 1.0,
    teammate_out_shift: float = 0.0,
    external_over_odds: Optional[float] = None,
) -> float:
    """Compute fair value probability for a player prop.

    Args:
        game_values: Last N game stat values (most recent first).
        line: The prop line (e.g., 27.5).
        matchup_shift: Points shift from matchup analysis.
        venue_shift: Points shift from home/away.
        b2b_penalty_pct: Penalty as fraction (e.g., 0.06 for 6%).
        pace_factor: Multiplier (1.0 = league average pace).
        teammate_out_shift: Points shift from teammate absence.
        external_over_odds: American odds from stat tracker (optional).

    Returns:
        Fair probability of clearing the line (0-1).
    """
    if not game_values:
        return 0.5

    mean_val = sum(game_values) / len(game_values)

    # Total shift
    total_shift = matchup_shift + venue_shift + teammate_out_shift
    total_shift -= b2b_penalty_pct * mean_val  # B2B penalty
    total_shift += (pace_factor - 1.0) * mean_val  # Pace adjustment

    # Apply shift to all values
    adjusted = [v + total_shift for v in game_values]

    # Weighted hit rate
    model_prob = weighted_hit_rate(adjusted, line)

    # Blend with external odds if available
    if external_over_odds is not None:
        ext_prob = implied_probability(external_over_odds)
        model_prob = 0.70 * model_prob + 0.30 * ext_prob

    return round(model_prob, 4)


def generate_book_b_signals(
    fair_values: list[dict],
    min_edge: float,
) -> list[Signal]:
    """Generate Book B signals from computed fair values.

    Each entry in fair_values:
        {"ticker": str, "fair_value": float, "kalshi_price": float,
         "player_id": int, "game_id": str}
    """
    signals = []
    for fv in fair_values:
        kalshi_dec = fv["kalshi_price"] / 100  # cents → decimal
        edge = fv["fair_value"] - kalshi_dec

        if edge >= min_edge:
            signals.append(Signal(
                book=Book.B,
                ticker=fv["ticker"],
                side="yes",
                edge=round(edge, 4),
                model_prob=fv["fair_value"],
                kalshi_price=kalshi_dec,
                metadata={"player_id": fv.get("player_id"),
                          "game_id": fv.get("game_id")},
            ))
        elif edge <= -min_edge:
            # Bet the under (buy NO)
            no_prob = 1.0 - fv["fair_value"]
            no_price = 1.0 - kalshi_dec
            signals.append(Signal(
                book=Book.B,
                ticker=fv["ticker"],
                side="no",
                edge=round(abs(edge), 4),
                model_prob=no_prob,
                kalshi_price=no_price,
                metadata={"player_id": fv.get("player_id"),
                          "game_id": fv.get("game_id")},
            ))

    return signals
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_book_b.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/books/book_b.py tests/test_book_b.py
git commit -m "feat: add Book B — pregame player props with empirical distribution"
```

---

### Task 12: Book C — Live event signals

**Files:**
- Create: `oracle/books/book_c.py`
- Create: `tests/test_book_c.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_book_c.py
from oracle.books.book_c import (
    detect_foul_trouble, detect_ot_likely, detect_blowout,
    LiveSignalType,
)

def test_foul_trouble_4th_foul_q3():
    signal = detect_foul_trouble(fouls=4, period="Q3", clock_seconds=400,
                                  player_name="LeBron", current_stat=18, line=27.5)
    assert signal is not None
    assert signal.signal_type == LiveSignalType.FOUL_TROUBLE
    assert signal.action == "sell_over"

def test_foul_trouble_3_fouls_ignored():
    signal = detect_foul_trouble(fouls=3, period="Q3", clock_seconds=400,
                                  player_name="LeBron", current_stat=18, line=27.5)
    assert signal is None

def test_foul_trouble_4_fouls_q4_ignored():
    # 4 fouls in Q4 is less significant (less time to lose)
    signal = detect_foul_trouble(fouls=4, period="Q4", clock_seconds=600,
                                  player_name="LeBron", current_stat=18, line=27.5)
    assert signal is None

def test_ot_likely_tied_under_2min():
    signal = detect_ot_likely(margin=0, period="Q4", clock_seconds=90,
                               player_name="LeBron", current_stat=24,
                               per_min_rate=0.75, line=27.5)
    assert signal is not None
    assert signal.signal_type == LiveSignalType.OT_LIKELY
    assert signal.action == "buy_over"

def test_ot_likely_not_tied():
    signal = detect_ot_likely(margin=5, period="Q4", clock_seconds=90,
                               player_name="LeBron", current_stat=24,
                               per_min_rate=0.75, line=27.5)
    assert signal is None

def test_ot_likely_but_already_cleared():
    # Player already at 30, line 27.5 → no need to buy over
    signal = detect_ot_likely(margin=0, period="Q4", clock_seconds=90,
                               player_name="LeBron", current_stat=30,
                               per_min_rate=0.75, line=27.5)
    assert signal is None

def test_blowout_detected():
    signal = detect_blowout(margin=22, period="Q3", clock_seconds=400,
                             player_name="LeBron", current_stat=18, line=27.5)
    assert signal is not None
    assert signal.signal_type == LiveSignalType.BLOWOUT
    assert signal.action == "sell_over"

def test_blowout_but_already_cleared():
    signal = detect_blowout(margin=22, period="Q3", clock_seconds=400,
                             player_name="LeBron", current_stat=30, line=27.5)
    assert signal is None  # Already over line, don't sell

def test_blowout_not_enough_margin():
    signal = detect_blowout(margin=15, period="Q3", clock_seconds=400,
                             player_name="LeBron", current_stat=18, line=27.5)
    assert signal is None  # Need 20+
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_book_c.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Book C**

```python
# oracle/books/book_c.py
"""Book C: Live event trading signals (foul trouble, OT, blowout)."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LiveSignalType(Enum):
    FOUL_TROUBLE = "foul_trouble"
    OT_LIKELY = "ot_likely"
    BLOWOUT = "blowout"


@dataclass
class LiveSignal:
    signal_type: LiveSignalType
    player_name: str
    action: str  # "buy_over", "sell_over"
    metadata: dict


def detect_foul_trouble(
    fouls: int,
    period: str,
    clock_seconds: int,
    player_name: str,
    current_stat: float,
    line: float,
) -> Optional[LiveSignal]:
    """Detect 4th foul before Q4 → sell the over."""
    if fouls < 4:
        return None
    if period not in ("Q1", "Q2", "Q3"):
        return None  # Q4 fouls matter less
    if current_stat >= line:
        return None  # Already cleared, no edge in selling

    return LiveSignal(
        signal_type=LiveSignalType.FOUL_TROUBLE,
        player_name=player_name,
        action="sell_over",
        metadata={"fouls": fouls, "period": period, "current": current_stat,
                  "line": line},
    )


def detect_ot_likely(
    margin: int,
    period: str,
    clock_seconds: int,
    player_name: str,
    current_stat: float,
    per_min_rate: float,
    line: float,
) -> Optional[LiveSignal]:
    """Detect tied game with < 2 min left in Q4 → buy the over.

    Only signal if OT production would push player over the line.
    """
    if abs(margin) > 2:
        return None
    if period != "Q4":
        return None
    if clock_seconds > 120:
        return None
    if current_stat >= line:
        return None  # Already cleared

    # Project: current + remaining_reg + 5 min OT
    remaining_reg_min = clock_seconds / 60
    ot_minutes = 5.0
    projected = current_stat + per_min_rate * (remaining_reg_min + ot_minutes)

    # Require 5% margin above line
    if projected < line * 1.05:
        return None

    return LiveSignal(
        signal_type=LiveSignalType.OT_LIKELY,
        player_name=player_name,
        action="buy_over",
        metadata={"margin": margin, "projected": round(projected, 1),
                  "line": line, "current": current_stat},
    )


def detect_blowout(
    margin: int,
    period: str,
    clock_seconds: int,
    player_name: str,
    current_stat: float,
    line: float,
    blowout_threshold: int = 20,
) -> Optional[LiveSignal]:
    """Detect 20+ point blowout in Q3+ → sell the over.

    Both teams' starters will sit most of Q4.
    """
    if abs(margin) < blowout_threshold:
        return None
    if period not in ("Q3", "Q4"):
        return None
    if current_stat >= line:
        return None  # Already cleared

    return LiveSignal(
        signal_type=LiveSignalType.BLOWOUT,
        player_name=player_name,
        action="sell_over",
        metadata={"margin": margin, "period": period,
                  "current": current_stat, "line": line},
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_book_c.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/books/book_c.py tests/test_book_c.py
git commit -m "feat: add Book C — live event signals (foul, OT, blowout)"
```

---

### Task 13: Quote quality checks (Book C execution filter)

**Files:**
- Create: `oracle/execution/quote_check.py`
- Create: `tests/test_quote_check.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_quote_check.py
from oracle.execution.quote_check import check_quote_quality, QuoteResult
from oracle.models import QuoteSnapshot
import time

def test_fresh_tight_deep_passes():
    quote = QuoteSnapshot(
        ticker="X", yes_bid=48, yes_ask=51,
        bid_depth=20, ask_depth=15, timestamp=time.time(),
    )
    result = check_quote_quality(quote, max_age_s=5, max_spread=8, min_depth=5)
    assert result.ok is True

def test_stale_quote_fails():
    quote = QuoteSnapshot(
        ticker="X", yes_bid=48, yes_ask=51,
        bid_depth=20, ask_depth=15, timestamp=time.time() - 10,
    )
    result = check_quote_quality(quote, max_age_s=5, max_spread=8, min_depth=5)
    assert result.ok is False
    assert "age" in result.reason

def test_wide_spread_fails():
    quote = QuoteSnapshot(
        ticker="X", yes_bid=40, yes_ask=55,
        bid_depth=20, ask_depth=15, timestamp=time.time(),
    )
    result = check_quote_quality(quote, max_age_s=5, max_spread=8, min_depth=5)
    assert result.ok is False
    assert "spread" in result.reason

def test_thin_depth_fails():
    quote = QuoteSnapshot(
        ticker="X", yes_bid=48, yes_ask=51,
        bid_depth=2, ask_depth=3, timestamp=time.time(),
    )
    result = check_quote_quality(quote, max_age_s=5, max_spread=8, min_depth=5)
    assert result.ok is False
    assert "depth" in result.reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quote_check.py -v`
Expected: FAIL

- [ ] **Step 3: Implement quote checks**

```python
# oracle/execution/quote_check.py
"""Quote quality filters for Book C live execution."""
from __future__ import annotations
from dataclasses import dataclass
from oracle.models import QuoteSnapshot


@dataclass
class QuoteResult:
    ok: bool
    reason: str = ""


def check_quote_quality(
    quote: QuoteSnapshot,
    max_age_s: float,
    max_spread: int,
    min_depth: int,
) -> QuoteResult:
    if quote.age_seconds > max_age_s:
        return QuoteResult(False, f"age={quote.age_seconds:.1f}s > {max_age_s}s")

    if quote.spread > max_spread:
        return QuoteResult(False, f"spread={quote.spread}c > {max_spread}c")

    min_side_depth = min(quote.bid_depth, quote.ask_depth)
    if min_side_depth < min_depth:
        return QuoteResult(False, f"depth={min_side_depth} < {min_depth}")

    return QuoteResult(True)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_quote_check.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/execution/quote_check.py tests/test_quote_check.py
git commit -m "feat: add quote quality checks for Book C execution"
```

---

### Task 14: Order executor

**Files:**
- Create: `oracle/execution/executor.py`
- Create: `tests/test_executor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_executor.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from oracle.execution.executor import OrderExecutor
from oracle.models import Book, Signal, Position

@pytest.fixture
def mock_kalshi():
    client = AsyncMock()
    client.place_order = AsyncMock(return_value={
        "order": {"order_id": "ord123", "status": "resting"}
    })
    client.cancel_order = AsyncMock(return_value={"order": {"status": "canceled"}})
    return client

@pytest.mark.asyncio
async def test_execute_limit_order(mock_kalshi):
    executor = OrderExecutor(mock_kalshi)
    signal = Signal(book=Book.B, ticker="KXNBAPTS-X", side="yes",
                    edge=0.12, model_prob=0.72, kalshi_price=0.60)
    result = await executor.place_limit(signal, contracts=10, price_cents=60)
    mock_kalshi.place_order.assert_called_once_with(
        ticker="KXNBAPTS-X", action="buy", side="yes",
        type_="limit", count=10, yes_price=60,
    )
    assert result["order"]["order_id"] == "ord123"

@pytest.mark.asyncio
async def test_cancel_order(mock_kalshi):
    executor = OrderExecutor(mock_kalshi)
    await executor.cancel("ord123")
    mock_kalshi.cancel_order.assert_called_once_with("ord123")

def test_compute_contracts():
    executor = OrderExecutor(None)
    contracts = executor.compute_contracts(
        bankroll=2000, position_pct=0.015, price_decimal=0.60,
    )
    # 2000 * 0.015 = $30 budget, $30 / $0.60 = 50 contracts
    assert contracts == 50

def test_compute_contracts_caps_at_zero():
    executor = OrderExecutor(None)
    assert executor.compute_contracts(bankroll=0, position_pct=0.015, price_decimal=0.60) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement executor**

```python
# oracle/execution/executor.py
"""Order placement, sizing, and cancellation."""
from __future__ import annotations
from oracle.models import Signal
from oracle.clients.kalshi import KalshiClient


class OrderExecutor:
    def __init__(self, kalshi: KalshiClient | None):
        self._kalshi = kalshi

    async def place_limit(self, signal: Signal, contracts: int,
                          price_cents: int) -> dict:
        return await self._kalshi.place_order(
            ticker=signal.ticker,
            action="buy",
            side=signal.side,
            type_="limit",
            count=contracts,
            yes_price=price_cents,
        )

    async def cancel(self, order_id: str) -> dict:
        return await self._kalshi.cancel_order(order_id)

    @staticmethod
    def compute_contracts(bankroll: float, position_pct: float,
                          price_decimal: float) -> int:
        if bankroll <= 0 or price_decimal <= 0:
            return 0
        budget = bankroll * position_pct
        return int(budget / price_decimal)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_executor.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add oracle/execution/executor.py tests/test_executor.py
git commit -m "feat: add order executor with fixed-fractional sizing"
```

---

## Chunk 4: Integration — Real WebSocket + Main Orchestrator

### Task 15: Real Sports Socket.io client

**Files:**
- Create: `oracle/clients/real_ws.py`

Note: Socket.io is hard to unit test with mocks. This task creates the client with manual integration test instructions rather than automated tests.

- [ ] **Step 1: Implement WebSocket client**

```python
# oracle/clients/real_ws.py
"""Real Sports App Socket.io client for live game data."""
from __future__ import annotations
import asyncio
from typing import Callable, Awaitable
import socketio
from hashids import Hashids
import time

_hashids = Hashids("realwebapp", 16)


class RealWebSocket:
    def __init__(self):
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_delay=0.25,
            reconnection_delay_max=1.0,
        )
        self._handlers: dict[str, list[Callable]] = {}
        self._connected = False
        self._last_data_time = 0.0

        self._sio.on("connect", self._on_connect)
        self._sio.on("disconnect", self._on_disconnect)

        # Register all relevant events
        for event in [
            "LiveFeedSocketPlaysAdded",
            "LiveFeedSocketPlaysUpdated",
            "LiveFeedSocketPlayersUpdated",
            "GameUpdated",
            "GameMarketUpdated",
            "PlayerBoxScoreUpdated",
        ]:
            self._sio.on(event, self._make_handler(event))

    def _make_handler(self, event_name: str):
        async def handler(data):
            self._last_data_time = time.time()
            for cb in self._handlers.get(event_name, []):
                await cb(data)
        return handler

    def on(self, event: str, callback: Callable[..., Awaitable]):
        self._handlers.setdefault(event, []).append(callback)

    async def connect(self, socket_type: str = "LiveFeed", **extra_query):
        query = {
            "socketType": socket_type,
            "realRequestToken": _hashids.encode(int(time.time() * 1000)),
            "realVersion": "28",
            **extra_query,
        }
        await self._sio.connect(
            "https://web.realsports.io",
            transports=["websocket"],
            socketio_path="/socket.io/",
            headers={},
            wait=True,
            wait_timeout=10,
        )
        self._connected = True

    async def disconnect(self):
        await self._sio.disconnect()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def seconds_since_data(self) -> float:
        if self._last_data_time == 0:
            return float("inf")
        return time.time() - self._last_data_time

    async def _on_connect(self):
        self._connected = True

    async def _on_disconnect(self):
        self._connected = False
```

- [ ] **Step 2: Commit**

```bash
git add oracle/clients/real_ws.py
git commit -m "feat: add Real Sports Socket.io WebSocket client"
```

---

### Task 16: Main orchestrator

**Files:**
- Create: `oracle/main.py`

- [ ] **Step 1: Implement the daily cycle orchestrator**

```python
# oracle/main.py
"""Oracle main entry point — daily cycle orchestrator."""
from __future__ import annotations
import asyncio
import logging
import sys
from datetime import date

from oracle.config import load_config
from oracle.db import OracleDB
from oracle.clients.real_rest import RealClient
from oracle.clients.kalshi import KalshiClient
from oracle.clients.real_ws import RealWebSocket
from oracle.risk.ledger import RiskLedger
from oracle.risk.limits import check_limits
from oracle.risk.fees import settlement_fee
from oracle.execution.executor import OrderExecutor
from oracle.execution.quote_check import check_quote_quality
from oracle.books.book_a import scan_divergence
from oracle.books.book_b import (
    compute_fair_value, generate_book_b_signals,
    check_lineup_gate, LineupGate,
)
from oracle.books.book_c import detect_foul_trouble, detect_ot_likely, detect_blowout
from oracle.models import Book, QuoteSnapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("oracle")


async def run(config_path: str = "config.yaml"):
    cfg = load_config(config_path)
    db = OracleDB("oracle.db")
    ledger = RiskLedger()

    # Initialize clients (credentials from env or config)
    # For now, placeholder — user fills in real credentials
    real = RealClient(
        user_id="YOUR_USER_ID",
        device_id="YOUR_DEVICE_ID",
        token="YOUR_TOKEN",
        device_uuid="YOUR_UUID",
    )
    kalshi = KalshiClient(
        key_id="YOUR_KEY_ID",
        private_key_path="kalshi_private_key.pem",
    )
    executor = OrderExecutor(kalshi)

    log.info("Oracle starting — bankroll=$%.0f", cfg.bankroll)

    try:
        # === PRE-GAME PHASE ===
        log.info("=== PRE-GAME: Fetching tonight's slate ===")
        today = date.today().isoformat()

        # Book A: scan for game divergence
        if cfg.books.a.enabled:
            log.info("Book A: scanning game divergence...")
            real_markets = await real.get_game_markets("nba")
            kalshi_game_markets = await kalshi.get_markets(
                series_ticker="KXNBAGAME", status="open"
            )
            # TODO: match Real games to Kalshi games by team/date
            # signals_a = scan_divergence(matched_real, matched_kalshi,
            #     min_edge=cfg.books.a.min_edge,
            #     min_volume=cfg.books.a.min_real_volume)
            log.info("Book A: scan complete")

        # Book B: compute prop fair values
        if cfg.books.b.enabled:
            log.info("Book B: computing prop fair values...")
            trackers = await real.get_stat_trackers(today, "nba")
            # TODO: for each player, fetch profile + season feed,
            # compute fair values, generate signals
            log.info("Book B: computation complete")

        # === LIVE PHASE ===
        log.info("=== LIVE: Starting WebSocket + polling loop ===")
        ws = RealWebSocket()

        # Book C event handlers
        async def on_plays_added(data):
            # TODO: parse play events, detect foul/OT/blowout
            pass

        async def on_players_updated(data):
            # TODO: update live player stats, check foul counts
            pass

        ws.on("LiveFeedSocketPlaysAdded", on_plays_added)
        ws.on("LiveFeedSocketPlayersUpdated", on_players_updated)

        try:
            await ws.connect("LiveFeed")
            log.info("WebSocket connected")
        except Exception as e:
            log.warning("WebSocket failed: %s — running REST-only", e)

        # Main polling loop
        log.info("Entering main loop (Ctrl+C to stop)")
        while True:
            # Check kill switch conditions
            if ledger.daily_pnl <= -(cfg.risk.daily_stop_loss_pct * cfg.bankroll):
                log.warning("DAILY STOP LOSS HIT: $%.2f — halting", ledger.daily_pnl)
                break

            # Poll Kalshi positions
            # TODO: reconcile with ledger

            await asyncio.sleep(10)

    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        await real.close()
        await kalshi.close()
        db.close()
        log.info("Oracle stopped. Daily P&L: $%.2f", ledger.daily_pnl)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (models, config, db, fees, ledger, limits, book_a, book_b, book_c, matching, quote_check, executor).

- [ ] **Step 3: Commit**

```bash
git add oracle/main.py
git commit -m "feat: add main orchestrator with daily cycle skeleton"
```

---

### Task 17: Final integration — run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 30+ tests, all PASS.

- [ ] **Step 2: Verify imports work end-to-end**

Run: `python -c "from oracle.main import run; print('Oracle ready')"`
Expected: `Oracle ready`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Oracle v1 complete — three-book NBA trading system"
```

---

## Summary

| Task | Component | Tests |
|---|---|---|
| 1 | Project scaffolding | — |
| 2 | Data models | 5 tests |
| 3 | Config loading | 2 tests |
| 4 | Fee calculation | 3 tests |
| 5 | SQLite database | 4 tests |
| 6 | Risk ledger + limits | 7 tests |
| 7 | Real REST client | 4 tests |
| 8 | Kalshi client | 4 tests |
| 9 | Player matching | 3 tests |
| 10 | Book A (divergence) | 4 tests |
| 11 | Book B (props) | 10 tests |
| 12 | Book C (live events) | 8 tests |
| 13 | Quote quality checks | 4 tests |
| 14 | Order executor | 4 tests |
| 15 | Real WebSocket | manual |
| 16 | Main orchestrator | integration |
| 17 | Final verification | full suite |

**Total: 17 tasks, ~62 automated tests, 17 commits.**

After implementation, the next steps are:
1. Fill in Real + Kalshi credentials in `config.yaml` / env vars
2. Build the game/player matching pipeline (connect Book B data fetch to fair value computation)
3. Paper trade on Kalshi demo for 4+ weeks
4. Add structured JSON trade logging
5. Build calibration dashboard (Brier score, CLV tracking)
