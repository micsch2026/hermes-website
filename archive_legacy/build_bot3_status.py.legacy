#!/usr/bin/env python3
"""
build_bot3_status.py — Generate API JSON for Bot #3 dashboard.

Bot #3 is now Mean Reversion v2 (Strategy Lab #57):
  - 12 FX pairs (from bot3_mr_v2.toml)
  - 1H timeframe
  - Per-pair SL/TP from MFO optimization

Reads:
  - /root/fx-bot/config/bot3_mr_v2.toml (strategy config)
  - /root/fx-bot/data/bot3_signals.json (current signals)
  - /root/fx-bot/data/bot3_positions.json (open positions)
  - /root/fx-bot/data/bot3_trades.jsonl (trade history)
  - /root/fx-bot/data/bot3_daemon_health.json (daemon health)
  - /root/fx-bot/data/bot3_engine_health.json (engine health)
  - /root/fx-bot/data/bot3_executor_health.json (executor health)
  - /root/fx-bot/data/bot3_balance.json (account balance)

Writes:
  - /root/.hermes/site/api/bot3/dashboard.json
"""

import json
import os
import datetime
import tomllib

API_DIR = "/root/.hermes/site/api/bot3"
DATA_DIR = "/root/fx-bot/data"
CONFIG_PATH = os.environ.get("BOT3_CONFIG", "/root/fx-bot/config/bot3_lab224.toml")


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default or {}


def load_jsonl(path):
    trades = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    except Exception:
        pass
    return trades


def load_config():
    """Load bot3 config to get the real pairs and strategy params.

    Supports BOTH formats:
    - Flat: [AUDCAD] (assets_lab0NN.toml)
    - Nested: [assets.AUDCAD] (old bot3_mr_v2.toml)
    """
    try:
        with open(CONFIG_PATH, "rb") as f:
            cfg = tomllib.load(f)
        defaults = cfg.get("DEFAULT", {})
        # Try nested [assets.XXX] first, then flat [XXX]
        assets = cfg.get("assets", {})
        if assets:
            pairs = sorted([s for s, a in assets.items() if a.get("enabled", True)])
        else:
            # Flat format: every key except DEFAULT is a pair
            assets = {k: v for k, v in cfg.items() if k != "DEFAULT"}
            pairs = sorted(assets.keys())
        return defaults, pairs, assets
    except Exception:
        return {}, [], {}

def _load_wfo_backtest(config_pairs):
    """Load backtest data from Strategy Lab catalog (strategy #61 = Bot 3)."""
    try:
        import sqlite3
        db = sqlite3.connect("/root/strategy-lab/catalog.db")
        db.row_factory = sqlite3.Row
        cur = db.cursor()
        # Strategy #61 = Bot 3's current Lab strategy (Lab #061)
        cur.execute("SELECT wfo_result, notes FROM strategies WHERE id=61")
        row = cur.fetchone()
        db.close()
        if not row:
            return {"total_pnl": 0, "active_pairs": " + ".join(config_pairs[:6]) + ("..." if len(config_pairs) > 6 else "")}

        wfo = json.loads(row["wfo_result"]) if isinstance(row["wfo_result"], str) else (row["wfo_result"] or {})
        notes = json.loads(row["notes"]) if row["notes"] else {}
        holdout = notes.get("holdout", {})

        return {
            "total_pnl": round(wfo.get("oos_pnl", 0)),
            "total_trades": wfo.get("oos_trades", 0),
            "win_rate": wfo.get("oos_wr", 0),
            "profit_factor": wfo.get("oos_pf", 0),
            "pass_rate": f"{round(wfo.get('oos_pass_rate', 0) * 100)}%",
            "expectancy": round(wfo.get("oos_pnl", 0) / max(wfo.get("oos_trades", 1), 1), 1),
            "active_pairs": " + ".join(config_pairs[:6]) + ("..." if len(config_pairs) > 6 else ""),
            "total_pairs": len(config_pairs),
            "wfo_id": 61,
            "wfo_splits": wfo.get("n_splits", 0),
            "wfo_pass_rate": round(wfo.get("oos_pass_rate", 0) * 100),
            "wfo_tier": wfo.get("tier", "?"),
            "decay_detected": wfo.get("decay_detected", False),
            "oos_profitable": int(round(wfo.get("oos_pass_rate", 0) * wfo.get("n_splits", 1))),
            "oos_total": wfo.get("n_splits", 0),
            "holdout_pnl": round(holdout.get("pnl", 0)),
            "holdout_pf": holdout.get("pf", 0),
            "holdout_wr": holdout.get("wr", 0),
            "holdout_trades": holdout.get("trades", 0),
            "holdout_passed": holdout.get("passed", False),
            "verdict": "✅ ROBUST" if wfo.get("tier") == "A" and holdout.get("passed") else "⚠️ Siehe Details",
        }
    except Exception as e:
        return {"total_pnl": 0, "error": str(e), "active_pairs": " + ".join(config_pairs[:6])}


def build():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Load config for real strategy info
    defaults, config_pairs, assets_cfg = load_config()

    # Load data
    signals = load_json(os.path.join(DATA_DIR, "bot3_signals.json"))
    positions = load_json(os.path.join(DATA_DIR, "bot3_positions.json"), [])
    trades = load_jsonl(os.path.join(DATA_DIR, "bot3_trades.jsonl"))
    daemon_health = load_json(os.path.join(DATA_DIR, "bot3_daemon_health.json"))
    engine_health = load_json(os.path.join(DATA_DIR, "bot3_daemon_health.json"))
    executor_health = load_json(os.path.join(DATA_DIR, "bot3_executor_health.json"))
    bot3_balance = load_json(os.path.join(DATA_DIR, "bot3_balance.json"))

    # Status
    daemon_ok = daemon_health.get("status") in ("ok", "market_closed", "started") or \
                engine_health.get("status") in ("ok", "market_closed")
    executor_ok = executor_health.get("status") in ("ok", "started", "market_closed")
    market_open = daemon_health.get("market_open", False) or engine_health.get("market_open", False)

    if daemon_ok and executor_ok:
        status = "active" if market_open else "waiting"
        status_text = "Active — Scanning" if market_open else "Waiting — Market Closed"
    else:
        status = "error"
        status_text = f"Error — Daemon: {daemon_health.get('status', '?')}"

    # Open positions
    open_positions = [p for p in positions if p.get("status") == "open"]
    for pos in open_positions:
        ts = pos.get("timestamp", "")
        if ts:
            try:
                entry_time = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                age = (datetime.datetime.now(datetime.timezone.utc) - entry_time).total_seconds() / 3600
                pos["age_hours"] = round(age, 1)
            except Exception:
                pos["age_hours"] = 0

    # Closed trades stats
    closed_actions = {"close", "close_time", "close_ctrader"}
    closed_trades = [t for t in trades if t.get("action") in closed_actions]
    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed_trades)
    winning = [t for t in closed_trades if (t.get("pnl", 0) or 0) > 0]
    losing = [t for t in closed_trades if (t.get("pnl", 0) or 0) <= 0]
    wr = len(winning) / len(closed_trades) * 100 if closed_trades else 0

    # Balance
    raw_balance = bot3_balance.get("balance", 0)
    money_digits = bot3_balance.get("money_digits", 2)
    balance = raw_balance / (10 ** money_digits) if raw_balance > 1000 else raw_balance

    # Per-pair info from config + tree pair_overrides
    tree_data = {}
    tree_file = defaults.get("tree_file", "")
    if tree_file and os.path.exists(tree_file):
        tree_data = load_json(tree_file, {})
    pair_overrides = tree_data.get("pair_overrides", {})
    tree_sl_def = tree_data.get("sl", {})
    tree_tp_def = tree_data.get("tp", {})

    per_pair = {}
    for sym in config_pairs:
        acfg = assets_cfg.get(sym, {})
        override = pair_overrides.get(sym, {})
        sl_cfg = override.get("sl", tree_sl_def)
        tp_cfg = override.get("tp", tree_tp_def)
        per_pair[sym] = {
            "sl_atr_mult": sl_cfg.get("mult", 1.5),
            "tp_r_mult": tp_cfg.get("value", 1.5),
            "pip_size": acfg.get("pip_size", 0.0001),
            "spread_normal": acfg.get("spread_normal", 1.0),
        }

    # Equity history from closed trades
    equity_history = []
    running_balance = balance - total_pnl
    for t in sorted(trades, key=lambda x: x.get("timestamp", "")):
        if t.get("action") in closed_actions and t.get("pnl") is not None:
            running_balance += t["pnl"]
            equity_history.append({
                "timestamp": t.get("timestamp", ""),
                "balance": round(running_balance, 2),
                "equity": round(running_balance, 2),
            })
    equity_history.append({
        "timestamp": now,
        "balance": round(balance, 2),
        "equity": round(balance, 2),
    })

    # Strategy info from config
    strategy_name = defaults.get("strategy", "mean_reversion")
    timeframe = defaults.get("timeframe", "1h")

    # Build dashboard
    dashboard = {
        "bot_id": "bot3",
        "name": "Bot #3 — Lab #061 MR (11 Pairs)",
        "timestamp": now,
        "demo": True,
        "account": {
            "balance": round(balance, 2),
            "equity": round(balance, 2),
            "currency": "EUR",
            "account_id": str(bot3_balance.get("account_id", "47444750")),
        },
        "equity_history": equity_history,
        "status": {
            "state": status,
            "text": status_text,
            "daemon": daemon_health,
            "executor": executor_health,
            "engine": engine_health,
        },
        "strategy": {
            "name": strategy_name,
            "timeframe": timeframe.upper(),
            "asset": f"{len(config_pairs)} FX Pairs",
            "pairs": config_pairs,
            "entry": defaults.get("strategy", "mean_reversion"),
        },
        "positions": open_positions,
        "signals": signals.get("signals", []),
        "active_signals": signals.get("signals", []),
        "total_signals": len(signals.get("signals", [])),
        "assets": config_pairs,
        "pairs": [{"symbol": p, "indicators": {}} for p in config_pairs],
        "performance": {
            "total_trades": len(closed_trades),
            "winning": len(winning),
            "losing": len(losing),
            "win_rate": round(wr, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(closed_trades), 2) if closed_trades else 0,
        },
        "backtest": _load_wfo_backtest(config_pairs),
        "indicators": {
            "rsi_period": defaults.get("rsi_period", 7),
            "bb_period": defaults.get("bb_period", 20),
            "kc_period": defaults.get("kc_period", 14),
        },
        "per_pair_params": per_pair,
    }

    # Write dashboard
    os.makedirs(API_DIR, exist_ok=True)
    out_path = os.path.join(API_DIR, "dashboard.json")
    with open(out_path, "w") as f:
        json.dump(dashboard, f, indent=2, default=str)
    print(f"Written: {out_path}")

    # Write performance heatmap from trades + positions
    heatmap = build_heatmap(config_pairs, trades, positions, now)
    heatmap_path = os.path.join(API_DIR, "performance_heatmap.json")
    with open(heatmap_path, "w") as f:
        json.dump(heatmap, f, indent=2, default=str)
    print(f"Written: {heatmap_path}")

    return dashboard


def build_heatmap(config_pairs, trades, positions, now):
    """Build per-pair performance heatmap from live trades, with WFO backtest fallback."""
    # Load WFO per-asset data as fallback when no live trades exist yet
    wfo_fallback = {}
    try:
        import sqlite3 as _sq
        _db = _sq.connect("/root/strategy-lab/catalog.db")
        _row = _db.execute("SELECT wfo_result FROM strategies WHERE id=61").fetchone()
        if _row:
            _wfo = json.loads(_row[0])
            for sym, data in _wfo.get("asset_results", {}).items():
                wfo_fallback[sym] = {
                    "bt_trades": data.get("oos_trades", 0),
                    "bt_wr": round(data.get("oos_wr", 0), 1),
                    "bt_pf": round(data.get("oos_pf", 0), 2),
                }
        _db.close()
    except Exception:
        pass

    pairs_data = {}
    total_wins = 0
    total_losses = 0
    total_trades = 0

    for sym in config_pairs:
        # Count closed trades for this symbol
        sym_trades = [t for t in trades
                      if t.get("symbol") == sym
                      and t.get("action") in ("close", "close_time", "close_ctrader")]
        wins = [t for t in sym_trades if (t.get("pnl", 0) or 0) > 0]
        losses = [t for t in sym_trades if (t.get("pnl", 0) or 0) <= 0]
        pnl = sum(t.get("pnl", 0) or 0 for t in sym_trades)
        wr = len(wins) / len(sym_trades) * 100 if sym_trades else 0

        # Open positions for this symbol
        open_count = sum(1 for p in positions
                        if p.get("symbol") == sym and p.get("status") == "open")

        entry = {
            "trades": len(sym_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 1),
            "total_pnl": round(pnl, 2),
            "open_positions": open_count,
            "label": sym,
        }
        # Enrich with WFO backtest data (always show, even with live trades)
        if sym in wfo_fallback:
            entry.update(wfo_fallback[sym])

        pairs_data[sym] = entry
        total_wins += len(wins)
        total_losses += len(losses)
        total_trades += len(sym_trades)

    return {
        "timestamp": now,
        "pairs": pairs_data,
        "summary": {
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "overall_win_rate": round(total_wins / total_trades * 100, 1) if total_trades else 0,
        },
    }


if __name__ == "__main__":
    build()
