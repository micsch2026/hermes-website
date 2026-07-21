#!/usr/bin/env python3
"""
build_self_learning.py — Generate Self-Learning Dashboard API data.

Reads:
  - /root/fx-bot/data/trades.jsonl (trade history)
  - /root/fx-bot/config/assets.toml (current parameters)

Generates:
  - /root/.hermes/site/api/self-learning/status.json  (current state)
  - /root/.hermes/site/api/self-learning/history.json  (parameter change log)

Usage:
    python3 build_self_learning.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Paths
TRADES_FILE = "/root/fx-bot/data/trades.jsonl"
ASSETS_FILE = "/root/fx-bot/config/assets.toml"
STATUS_OUT = "/root/.hermes/site/api/self-learning/status.json"
HISTORY_OUT = "/root/.hermes/site/api/self-learning/history.json"
PARAM_HISTORY_FILE = "/root/fx-bot/data/self_learning_history.jsonl"

# Rolling window size
ROLLING_WINDOW = 20


def parse_toml_simple(path):
    """Simple TOML parser for our flat config files."""
    sections = {}
    current = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                current = line[1:-1]
                sections[current] = {}
            elif '=' in line and current is not None:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                # Remove quotes
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                elif val.startswith("'") and val.endswith("'"):
                    val = val[1:-1]
                # Try numeric
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                sections[current][key] = val
    return sections


def load_trades(path):
    """Load all trades from JSONL."""
    trades = []
    if not os.path.exists(path):
        return trades
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return trades


def load_param_history(path):
    """Load parameter change history from JSONL."""
    events = []
    if not os.path.exists(path):
        return events
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def compute_rolling_metrics(trades, window=ROLLING_WINDOW):
    """Compute rolling-window metrics per pair."""
    # Group closed trades by pair
    pair_trades = defaultdict(list)
    for t in trades:
        status = t.get('status', '')
        if status == 'open':
            continue
        pair = t.get('symbol', 'UNKNOWN')
        pnl = t.get('pnl', t.get('cTrader_profit', 0))
        if pnl is None:
            pnl = 0
        pair_trades[pair].append({
            'pnl': float(pnl),
            'timestamp': t.get('timestamp', ''),
            'side': t.get('side', ''),
            'score': t.get('score', 0),
            'status': status,
        })

    results = {}
    for pair, ptrades in pair_trades.items():
        # Sort by timestamp descending, take last N
        ptrades.sort(key=lambda x: x['timestamp'], reverse=True)
        recent = ptrades[:window]

        wins = [t for t in recent if t['pnl'] > 0]
        losses = [t for t in recent if t['pnl'] < 0]
        total = len(recent)

        if total == 0:
            continue

        win_rate = len(wins) / total * 100
        avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t['pnl'] for t in losses) / len(losses)) if losses else 0
        total_pnl = sum(t['pnl'] for t in recent)
        avg_pnl = total_pnl / total

        # Profit Factor
        gross_profit = sum(t['pnl'] for t in wins)
        gross_loss = abs(sum(t['pnl'] for t in losses))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Kelly Fraction
        rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        kelly = 0
        if rr_ratio > 0:
            kelly = (win_rate / 100 * rr_ratio - (1 - win_rate / 100)) / rr_ratio
            kelly = max(0.01, min(kelly, 0.10))

        # Rolling PnL series for chart
        rolling_pnl = []
        cumulative = 0
        for t in reversed(recent):
            cumulative += t['pnl']
            rolling_pnl.append({
                'timestamp': t['timestamp'],
                'pnl': round(t['pnl'], 2),
                'cumulative': round(cumulative, 2),
            })

        results[pair] = {
            'total_trades': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(win_rate, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(total_pnl, 2),
            'profit_factor': round(pf, 2) if pf != float('inf') else 99.99,
            'rr_ratio': round(rr_ratio, 2),
            'kelly_fraction': round(kelly * 100, 2),  # as percentage
            'rolling_pnl': rolling_pnl,
            'last_trade_at': recent[0]['timestamp'] if recent else None,
        }

    return results


def compute_global_metrics(trades):
    """Compute overall bot metrics."""
    closed = [t for t in trades if t.get('status', '') != 'open']
    if not closed:
        return {}

    # Sort by timestamp ascending for first/last
    closed_by_time = sorted(closed, key=lambda t: t.get('timestamp', ''))

    total = len(closed)
    wins = [t for t in closed if (t.get('pnl', 0) or 0) > 0]
    losses = [t for t in closed if (t.get('pnl', 0) or 0) < 0]
    total_pnl = sum(t.get('pnl', 0) or 0 for t in closed)

    return {
        'total_trades': total,
        'total_wins': len(wins),
        'total_losses': len(losses),
        'global_win_rate': round(len(wins) / total * 100, 1) if total > 0 else 0,
        'global_pnl': round(total_pnl, 2),
        'first_trade': closed_by_time[0].get('timestamp') if closed_by_time else None,
        'last_trade': closed_by_time[-1].get('timestamp') if closed_by_time else None,
    }


def build_status(assets_config, rolling_metrics, global_metrics, param_history):
    """Build the status.json structure."""
    pairs = []
    for section, params in assets_config.items():
        if section == 'DEFAULT':
            continue
        if 'strategy' not in params:
            continue

        pair_data = {
            'pair': section,
            'strategy': params.get('strategy', 'unknown'),
            'parameters': {
                'sl_pips': params.get('sl_pips', 0),
                'tp_pips': params.get('tp_pips', 0),
                'rsi_period': params.get('rsi_period', 7),
                'rsi_oversold': params.get('rsi_oversold', 30),
                'rsi_overbought': params.get('rsi_overbought', 70),
                'bb_mult': params.get('bb_mult', 2.0),
                'kc_mult': params.get('kc_mult', 1.5),
                'min_body_ratio': params.get('min_body_ratio', 0.5),
                'direction': params.get('direction', 'both'),
            },
            'metrics': rolling_metrics.get(section, {}),
            'last_adjustment': None,
        }

        # Find last adjustment for this pair
        for evt in reversed(param_history):
            if evt.get('pair') == section:
                pair_data['last_adjustment'] = evt
                break

        pairs.append(pair_data)

    # Sort by total_pnl descending
    pairs.sort(key=lambda p: p.get('metrics', {}).get('total_pnl', 0), reverse=True)

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'rolling_window': ROLLING_WINDOW,
        'global': global_metrics,
        'pairs': pairs,
        'bounds': {
            'sl_pips': {'min': 25, 'max': 200},
            'tp_pips': {'min': 25, 'max': 300},
            'rsi_oversold': {'min': 15, 'max': 40},
            'rsi_overbought': {'min': 60, 'max': 85},
            'bb_mult': {'min': 1.0, 'max': 4.0},
            'kc_mult': {'min': 1.0, 'max': 4.0},
            'min_body_ratio': {'min': 0.10, 'max': 0.80},
        },
    }


def build_history(param_history, rolling_metrics):
    """Build the history.json structure."""
    events = []
    for evt in param_history:
        events.append({
            'timestamp': evt.get('timestamp', ''),
            'pair': evt.get('pair', ''),
            'parameter': evt.get('parameter', ''),
            'old_value': evt.get('old_value'),
            'new_value': evt.get('new_value'),
            'reason': evt.get('reason', ''),
            'metrics_snapshot': evt.get('metrics_snapshot', {}),
        })

    # Add synthetic "initial" events from current config if no history exists
    if not events:
        events.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'pair': '*',
            'parameter': 'system',
            'old_value': None,
            'new_value': 'Self-Learning Monitor initialized (Phase 1: Monitoring only)',
            'reason': 'Initial deployment — no auto-adjustments yet',
            'metrics_snapshot': {},
        })

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_events': len(events),
        'events': events,
    }


def main():
    print("[self-learning] Loading assets config...")
    assets_config = parse_toml_simple(ASSETS_FILE)

    print("[self-learning] Loading trades...")
    trades = load_trades(TRADES_FILE)
    print(f"[self-learning]   {len(trades)} trades loaded")

    print("[self-learning] Loading parameter history...")
    param_history = load_param_history(PARAM_HISTORY_FILE)
    print(f"[self-learning]   {len(param_history)} history events")

    print("[self-learning] Computing rolling metrics...")
    rolling = compute_rolling_metrics(trades)

    print("[self-learning] Computing global metrics...")
    global_m = compute_global_metrics(trades)

    print("[self-learning] Building status.json...")
    status = build_status(assets_config, rolling, global_m, param_history)

    print("[self-learning] Building history.json...")
    history = build_history(param_history, rolling)

    # Write outputs
    os.makedirs(os.path.dirname(STATUS_OUT), exist_ok=True)
    with open(STATUS_OUT, 'w') as f:
        json.dump(status, f, indent=2, default=str)
    print(f"[self-learning]   → {STATUS_OUT}")

    with open(HISTORY_OUT, 'w') as f:
        json.dump(history, f, indent=2, default=str)
    print(f"[self-learning]   → {HISTORY_OUT}")

    # Summary
    pairs_with_data = sum(1 for p in status['pairs'] if p.get('metrics', {}).get('total_trades', 0) > 0)
    print(f"\n[self-learning] DONE: {len(status['pairs'])} pairs, {pairs_with_data} with trade data")
    print(f"[self-learning] Global: {global_m.get('total_trades', 0)} trades, "
          f"WR {global_m.get('global_win_rate', 0)}%, "
          f"PnL {global_m.get('global_pnl', 0)}€")


if __name__ == '__main__':
    main()
