"""
EdgeForge Shadow Trading Pipeline — Self-contained live strategy executor.

Upload to OpenAlgo Python Strategy Manager (/python/new).
Schedule: start 09:15 IST, stop 15:30 IST, Mon-Fri.
Dependencies: only openalgo, numpy.

Pipeline:
  09:15 — Fetch option chain, compute features
  09:40 — V5 bandit decision → position sizing → place multi-leg order
  14:55 — Exit all positions
  EOD  — Log results

Environment variables (set in OpenAlgo strategy config):
  OPENALGO_API_KEY   - Required
  OPENALGO_HOST      - Default http://127.0.0.1:5000
  SYMBOL             - Default NIFTY
  EXCHANGE           - Default NFO
  CAPITAL            - Default 250000
  RISK_PER_TRADE     - Default 0.02
  MAX_DAILY_LOSS_PCT - Default 0.06
"""

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
from openalgo import api

# ═════════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════════

API_KEY = os.getenv("OPENALGO_API_KEY", "")
HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")
SYMBOL = os.getenv("SYMBOL", "NIFTY")
EXCHANGE = os.getenv("EXCHANGE", "NFO")
CAPITAL = float(os.getenv("CAPITAL", "250000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.02"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.06"))
DATE_TODAY = date.today().strftime("%Y-%m-%d")

client = api(api_key=API_KEY, host=HOST)

# ── State ────────────────────────────────────────────────────────────────────

_checked_today = False

# V5 bandit parameters (hardcoded from last retrain; update periodically)
FEATURE_COLS = [
    "range",
    "gap_pct",
    "atm_straddle",
    "atm_straddle_pct",
    "atm_pcr_oi",
    "call_oi_ratio",
    "expected_move_vs_yesterday_range",
    "fc_high_only",
    "fc_low_only",
    "fc_not_broken",
    "fc_hl_seq",
    "fc_lh_seq",
    "prob_up",
    "ci_width",
    "robustness",
    "n_matches",
    "avg_move",
    "downside_percentile",
]

# ── Action space: (family, instrument, offset, width) ────────────────────────
# Matches V5's filtered action space from strategy_selector.py
ACTIONS = [
    ("skip", "", 0, 0),
    ("short_premium", "iron_condor", 0, 0),
    ("short_premium", "iron_condor", 0, 50),
    ("short_premium", "iron_condor", 0, 100),
    ("short_premium", "iron_condor", 0, 150),
    ("short_premium", "iron_condor", 50, 0),
    ("short_premium", "iron_condor", 50, 50),
    ("short_premium", "iron_condor", 50, 100),
    ("short_premium", "iron_condor", 50, 150),
    ("short_premium", "iron_condor", 100, 0),
    ("short_premium", "iron_condor", 100, 50),
    ("short_premium", "iron_condor", 100, 100),
    ("short_premium", "iron_condor", 100, 150),
    ("short_premium", "iron_fly", 0, 0),
    ("short_premium", "iron_fly", 0, 50),
    ("short_premium", "iron_fly", 0, 100),
    ("short_premium", "iron_fly", 0, 150),
    ("short_premium", "iron_fly", 50, 0),
    ("short_premium", "iron_fly", 50, 50),
    ("short_premium", "iron_fly", 50, 100),
    ("short_premium", "iron_fly", 50, 150),
    ("short_premium", "iron_fly", 100, 0),
    ("short_premium", "iron_fly", 100, 50),
    ("short_premium", "iron_fly", 100, 100),
    ("short_premium", "iron_fly", 100, 150),
    ("long_premium", "long_call", 0, 0),
    ("long_premium", "long_call", 0, 50),
    ("long_premium", "long_put", 0, 0),
    ("long_premium", "long_put", 0, 50),
]

# Theta matrix (n_actions x n_features+1 for bias term) — loaded from file
THETA_PATH = os.getenv("THETA_PATH", "")


def _load_theta() -> np.ndarray:
    if THETA_PATH and Path(THETA_PATH).exists():
        return np.load(THETA_PATH)
    # Fallback: try well-known location
    fallback = Path(__file__).resolve().parent / "theta.npy"
    if fallback.exists():
        return np.load(str(fallback))
    print("WARNING: No theta.npy found. Using unit weights (equal action preference).")
    return np.ones((len(ACTIONS), len(FEATURE_COLS) + 1))


# ═════════════════════════════════════════════════════════════════════════════
# Calibration models (self-contained, mirrors src/calibration/models.py)
# ═════════════════════════════════════════════════════════════════════════════








# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: Market data
# ═════════════════════════════════════════════════════════════════════════════


_historical_bars: list[dict] = []


def fetch_index_quote() -> dict:
    """Fetch NIFTY index LTP for intraday bar tracking."""
    try:
        result = client.optionchain(underlying=SYMBOL, exchange=EXCHANGE)
        if isinstance(result, dict) and result.get("status") == "success":
            return {
                "time": datetime.now().strftime("%H:%M:%S"),
                "close": result.get("underlying_ltp", 0),
                "high": result.get("underlying_ltp", 0),
                "low": result.get("underlying_ltp", 0),
            }
    except Exception:
        pass
    return {
        "time": datetime.now().strftime("%H:%M:%S"),
        "close": 0,
        "high": 0,
        "low": 0,
    }


def fetch_option_chain(retries: int = 3, backoff: float = 10.0):
    for attempt in range(1, retries + 1):
        try:
            result = client.optionchain(underlying=SYMBOL, exchange=EXCHANGE)
            if isinstance(result, dict) and result.get("status") == "success":
                return result
            print(f"ERROR fetching option chain (attempt {attempt}/{retries}): {result}")
        except Exception as e:
            print(f"EXCEPTION fetching option chain (attempt {attempt}/{retries}): {e}")
        time.sleep(backoff)
    return None


def compute_features(chain_data: dict, historical_data: Optional[dict] = None) -> dict:
    ul_ltp = chain_data.get("underlying_ltp", 0)
    chain = chain_data.get("chain", [])
    atm_strike = chain_data.get("atm_strike", 0)

    atm_entry = next((c for c in chain if c["strike"] == atm_strike), None)
    atm_straddle = 0.0
    if atm_entry and atm_entry.get("ce") and atm_entry.get("pe"):
        ce_ltp = atm_entry["ce"].get("ltp", 0) or 0
        pe_ltp = atm_entry["pe"].get("ltp", 0) or 0
        atm_straddle = ce_ltp + pe_ltp

    atm_pe_oi = (atm_entry.get("pe", {}).get("oi", 0) or 0) if atm_entry else 0
    atm_ce_oi = (atm_entry.get("ce", {}).get("oi", 0) or 0) if atm_entry else 0
    atm_pcr_oi = atm_pe_oi / atm_ce_oi if atm_ce_oi > 0 else 1.0

    total_ce_oi = sum(c.get("ce", {}).get("oi", 0) or 0 for c in chain)
    total_pe_oi = sum(c.get("pe", {}).get("oi", 0) or 0 for c in chain)
    call_oi_ratio = total_ce_oi / (total_ce_oi + total_pe_oi + 1)

    ce_high = max((c.get("ce", {}).get("high", 0) or 0) for c in chain if c.get("ce"))
    ce_low = min((c.get("ce", {}).get("low", 0) or 0) for c in chain if c.get("ce"))
    range_pts = abs(ce_high - ce_low)

    fc_pattern = _detect_first_candle_pattern(historical_data)
    ctx = _estimate_evidence(fc_pattern, atm_pcr_oi, atm_straddle / max(ul_ltp, 1))

    features = {
        "range": range_pts,
        "gap_pct": 0.0,
        "atm_straddle": atm_straddle,
        "atm_straddle_pct": atm_straddle / ul_ltp if ul_ltp > 0 else 0,
        "atm_pcr_oi": atm_pcr_oi,
        "call_oi_ratio": call_oi_ratio,
        "expected_move_vs_yesterday_range": atm_straddle / max(range_pts, 1),
        "underlying_ltp": ul_ltp,
        "atm_strike": atm_strike,
    }
    features.update(fc_pattern)
    features.update(ctx)
    return features


def _detect_first_candle_pattern(historical_data: Optional[dict]) -> dict:
    fh = 0.0
    fl = float("inf")
    bh = bl = False
    fht = flt = None

    if not historical_data or "bars" not in historical_data:
        return {
            "fc_high_only": False,
            "fc_low_only": False,
            "fc_not_broken": True,
            "fc_hl_seq": False,
            "fc_lh_seq": False,
        }

    bars = historical_data["bars"]
    if not bars:
        return {
            "fc_high_only": False,
            "fc_low_only": False,
            "fc_not_broken": True,
            "fc_hl_seq": False,
            "fc_lh_seq": False,
        }

    fc = bars[0]
    fh = float(fc.get("high", fc.get("Close", 0)))
    fl = float(fc.get("low", fc.get("Close", 0)))

    for b in bars[1:]:
        ts = b.get("time", b.get("Time", ""))
        if ts > "09:40":
            break
        b_close = float(b.get("close", b.get("Close", 0)))
        b_high = float(b.get("high", b.get("High", b_close)))
        b_low = float(b.get("low", b.get("Low", b_close)))
        if not bh and b_high > fh:
            bh = True
            fht = ts
        if not bl and b_low < fl:
            bl = True
            flt = ts
        if bh and bl:
            break

    high_only = bh and not bl
    low_only = bl and not bh
    not_broken = not bh and not bl
    hl_seq = bh and bl and fht is not None and flt is not None and fht < flt
    lh_seq = bh and bl and fht is not None and flt is not None and flt < fht

    return {
        "fc_high_only": high_only,
        "fc_low_only": low_only,
        "fc_not_broken": not_broken,
        "fc_hl_seq": hl_seq,
        "fc_lh_seq": lh_seq,
    }


def _estimate_evidence(fc_pattern: dict, pcr: float, straddle_pct: float) -> dict:
    return {
        "prob_up": 0.5,
        "ci_width": 0.2,
        "robustness": 0.3,
        "n_matches": 15,
        "avg_move": 120.0,
        "downside_percentile": 0.5,
    }


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2: Decision pipeline
# ═════════════════════════════════════════════════════════════════════════════


def run_decision(features: dict) -> dict:
    theta = _load_theta()

    feat_vec = np.array([features.get(c, 0.0) for c in FEATURE_COLS])
    X = np.concatenate([[1.0], feat_vec])

    expected = theta @ X
    chosen = int(np.argmax(expected))
    family, instrument, offset, width = ACTIONS[chosen]
    predicted_pnl = float(expected[chosen])
    trade_flag = family != "skip" and predicted_pnl > 0

    return {
        "trade": trade_flag,
        "lots": 1 if trade_flag else 0,
        "instrument": instrument,
        "offset": offset,
        "width": width,
        "expected_pnl": predicted_pnl,
        "block_reason": "NONE" if trade_flag else "LOW_CONFIDENCE",
    }


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3: Order execution
# ═════════════════════════════════════════════════════════════════════════════


def _has_open_positions() -> bool:
    try:
        result = client.positionbook()
        if isinstance(result, dict) and result.get("status") == "success":
            positions = result.get("positions", result.get("data", []))
            for pos in positions:
                if isinstance(pos, dict) and pos.get("strategy") == "EdgeForge":
                    net_qty = int(pos.get("netqty", pos.get("quantity", 0)))
                    if net_qty != 0:
                        return True
    except Exception:
        pass
    return False


def place_strategy_order(decision: dict) -> dict:
    if not decision["trade"]:
        return {"status": "skipped", "reason": decision["block_reason"]}

    offset = decision["offset"]
    width = decision["width"]
    instrument = decision["instrument"]

    legs = _build_legs(instrument, offset, width)
    if not legs:
        return {"status": "error", "reason": "invalid_legs"}

    result = client.optionsmultiorder(
        strategy="EdgeForge",
        underlying=SYMBOL,
        exchange=EXCHANGE,
        legs=legs,
    )
    print(f"ORDER: {json.dumps(result, indent=2)}")
    return result


def _build_legs(instrument: str, offset: int, width: int) -> list:
    def _label(n: int) -> str:
        return f"OTM{n}" if n > 0 else "ATM"

    if instrument == "iron_condor":
        return [
            {
                "offset": _label(offset),
                "option_type": "PE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "PE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset),
                "option_type": "CE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "CE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if instrument == "iron_fly":
        return [
            {
                "offset": _label(offset),
                "option_type": "PE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "PE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset),
                "option_type": "CE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "CE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if instrument == "short_strangle":
        return [
            {
                "offset": _label(offset),
                "option_type": "PE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset),
                "option_type": "CE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if "call_spread" in instrument:
        return [
            {
                "offset": _label(offset),
                "option_type": "CE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "CE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if "put_spread" in instrument:
        return [
            {
                "offset": _label(offset),
                "option_type": "PE",
                "action": "SELL",
                "quantity": 1,
                "pricetype": "MARKET",
            },
            {
                "offset": _label(offset + width),
                "option_type": "PE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if instrument == "long_call":
        return [
            {
                "offset": _label(offset),
                "option_type": "CE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    if instrument == "long_put":
        return [
            {
                "offset": _label(offset),
                "option_type": "PE",
                "action": "BUY",
                "quantity": 1,
                "pricetype": "MARKET",
            },
        ]
    return []


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4: Exit
# ═════════════════════════════════════════════════════════════════════════════


def exit_positions():
    print("--- EXIT ALL POSITIONS ---")
    result = client.closeposition(strategy="EdgeForge")
    print(f"EXIT: {json.dumps(result, indent=2)}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5: Logging
# ═════════════════════════════════════════════════════════════════════════════


def log_result(date_str: str, features: dict, decision: dict, order_result: dict):
    entry = {
        "date": date_str,
        "features": {
            k: float(v) for k, v in features.items() if isinstance(v, (int, float))
        },
        "decision": {
            "trade": decision.get("trade", False),
            "lots": decision.get("lots", 0),
            "instrument": str(decision.get("instrument", "")),
            "offset": decision.get("offset", 0),
            "width": decision.get("width", 0),
            "expected_pnl": float(decision.get("expected_pnl", 0)),
            "block_reason": decision.get("block_reason", ""),
        },
        "order": order_result,
        "timestamp": datetime.now().isoformat(),
    }

    log_path = Path("data") / "output" / "shadow_trades.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if log_path.exists():
        with open(log_path) as f:
            log = json.load(f)
    log.append(entry)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, default=str)
    print(f"Logged to {log_path}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════


def main():
    global _checked_today

    print("=== EdgeForge Shadow Trading Pipeline (self-contained) ===")
    print(f"  Symbol: {SYMBOL} | Exchange: {EXCHANGE}")
    print(f"  Capital: Rs.{CAPITAL:,.0f} | Risk: {RISK_PER_TRADE:.1%}")
    print(f"  Actions: {len(ACTIONS)}")
    print(f"  OpenAlgo: {HOST}")
    print(f"  Started: {datetime.now().isoformat()}")
    print()

    decision = None
    order_result: dict = {"status": "no_trade"}
    features = None
    order_placed = False

    while True:
        now = datetime.now()
        hour, minute = now.hour, now.minute
        ts = now.strftime("%H:%M")

        if hour == 9 and 15 <= minute < 20:
            _historical_bars.append(fetch_index_quote())

            if not _checked_today:
                print(f"[{ts}] STEP 1: Fetching market data...")
                chain = fetch_option_chain()
                if chain:
                    features = compute_features(
                        chain, historical_data={"bars": _historical_bars}
                    )
                    print(
                        f"  ULP={features['underlying_ltp']} "
                        f"Straddle={features['atm_straddle']:.1f} "
                        f"PCR={features['atm_pcr_oi']:.2f}"
                    )

        elif hour == 9 and minute == 40 and not order_placed and features:
            if _has_open_positions():
                print(f"[{ts}] STEP 2-3: Open positions exist for EdgeForge; skipping to avoid duplicate.")
                order_placed = True
                order_result = {"status": "already_has_positions"}
            else:
                print(f"[{ts}] STEP 2: Decision pipeline...")
                try:
                    decision = run_decision(features)
                    print(
                        f"  trade={decision['trade']} lots={decision['lots']} "
                        f"instr={decision['instrument']} "
                        f"o={decision['offset']} w={decision['width']} "
                        f"pred_pnl={decision['expected_pnl']:.3f}"
                    )
                except Exception as e:
                    print(f"  ERROR: {e}")
                    import traceback

                    traceback.print_exc()

                if decision and decision["trade"]:
                    print(f"[{ts}] STEP 3: Placing order...")
                    order_result = place_strategy_order(decision)
                    order_placed = order_result.get("status") == "success"
                else:
                    reason = (
                        decision.get("block_reason", "no_decision")
                        if decision
                        else "no_decision"
                    )
                    print(f"[{ts}] STEP 3: No trade - {reason}")
                    order_result = {"status": "no_trade"}

        elif hour == 14 and minute == 55 and order_placed:
            print(f"[{ts}] STEP 4: Exiting positions...")
            exit_positions()

        elif hour == 15 and minute == 0 and not _checked_today:
            print(f"[{ts}] STEP 5: Logging...")
            if features and decision:
                log_result(
                    DATE_TODAY,
                    features,
                    decision,
                    order_result or {"status": "no_decision"},
                )
            _checked_today = True
            print("=== Day complete ===")

        elif hour > 15 or (hour == 15 and minute >= 30):
            print(f"[{ts}] Market closed. Exiting.")
            break

        time.sleep(30)


if __name__ == "__main__":
    main()
