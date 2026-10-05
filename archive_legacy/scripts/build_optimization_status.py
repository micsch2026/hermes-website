#!/usr/bin/env python3
"""
build_optimization_status.py — Transforms Grid-Search JSON into visualization-ready format.

Reads all grid search result files from /root/fx-bot/data/ and produces
a single optimization.json for the dashboard.

Supported input formats:
  1. bot2_grid_results.json    — EMA+ADX 5D grid (fast, slow, adx, sl, tp)
  2. portfolio_grid_search.json — Portfolio 2D grid (max_positions, risk_pct)
  3. grid_optimize_v2_results.json — Bot #1 10D grid (rsi, bb, sl, tp, etc.)
  4. grid_search_results.json  — SL/TP grid per pair
  5. grid_search_rr_results.json — Risk-Reward grid per pair
  6. grid_search_momentum.json — Momentum params grid
  7. grid_optimize_results.json — v1 optimization
  8. optimizer/bot2_bos_ob_grid.json — BOS+OB grid (new optimizer)
  9. optimizer/session_filter_results.json — Session filter analysis

Output: /root/.hermes/site/src/data/optimization.json
"""

import itertools
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

DATA_DIR = "/root/fx-bot/data"
DB_PATH = os.path.join(DATA_DIR, "optimizer", "optimization.db")
OUTPUT_DIR = "/root/.hermes/site/src/data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "optimization.json")


def load_json(path):
    """Load JSON file, return None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARN: Could not load {path}: {e}")
        return None


def flatten_bot2_grid(data):
    """Transform bot2_grid_results.json into heatmap-ready format.
    
    Input: {best_per_pair: {pair: {...}}, all_results: {pair: [{fast, slow, adx, sl, tp, trades, wr, pf, total_pips, ...}]}}
    Output: [{pair, fast, slow, adx, sl, tp, trades, wr, pf, total_pips, sl_rate, avg_pips}]
    """
    rows = []
    all_results = data.get("all_results", {})
    for pair, configs in all_results.items():
        for c in configs:
            rows.append({
                "source": "bot2_ema_adx",
                "pair": pair,
                "fast": c.get("fast"),
                "slow": c.get("slow"),
                "adx": c.get("adx"),
                "sl": c.get("sl"),
                "tp": c.get("tp"),
                "trades": c.get("trades", 0),
                "wr": c.get("wr", 0),
                "pf": c.get("pf", 0),
                "total_pips": c.get("total_pips", 0),
                "sl_rate": c.get("sl_rate", 0),
                "avg_pips": c.get("avg_pips", 0),
            })
    return rows


def flatten_portfolio_grid(data):
    """Transform portfolio_grid_search.json.
    
    Input: [{max_positions, risk_pct, final_equity, return_pct, max_dd_pct, calmar, ...}]
    Output: [{source, max_positions, risk_pct, return_pct, max_dd_pct, calmar, win_rate, profit_factor, ...}]
    """
    rows = []
    for c in data:
        rows.append({
            "source": "portfolio",
            "pair": "PORTFOLIO",
            "max_positions": c.get("max_positions"),
            "risk_pct": c.get("risk_pct"),
            "return_pct": c.get("return_pct", 0),
            "max_dd_pct": c.get("max_dd_pct", 0),
            "calmar": c.get("calmar", 0),
            "win_rate": c.get("win_rate", 0),
            "profit_factor": c.get("profit_factor", 0),
            "total_trades": c.get("total_trades", 0),
            "final_equity": c.get("final_equity", 0),
            "avg_pnl": c.get("avg_pnl", 0),
        })
    return rows


def flatten_grid_optimize_v2(data):
    """Transform grid_optimize_v2_results.json.
    
    Input: {pair: {tested, passed, best: {is: {...}, oos: {...}, params: {...}, combined_quality}}}
    Output: flattened rows with IS/OOS metrics + params
    """
    rows = []
    for pair, info in data.items():
        best = info.get("best")
        if not best:
            continue
        params = best.get("params", {})
        is_metrics = best.get("is", {})
        oos_metrics = best.get("oos", {})
        row = {
            "source": "grid_optimize_v2",
            "pair": pair,
            "tested": info.get("tested", 0),
            "passed": info.get("passed", 0),
            "combined_quality": best.get("combined_quality", 0),
        }
        # Add IS metrics with prefix
        for k, v in is_metrics.items():
            if k != "params":
                row[f"is_{k}"] = v
        # Add OOS metrics with prefix
        for k, v in oos_metrics.items():
            if k != "params":
                row[f"oos_{k}"] = v
        # Add params
        for k, v in params.items():
            row[f"param_{k}"] = v
        rows.append(row)
    return rows


def flatten_sl_tp_grid(data):
    """Transform grid_search_results.json (SL/TP per pair).
    
    Input: {pair: {current: {...}, optimal: {...}, top5: [...]}}
    Output: [{pair, sl_pips, tp_pips, rr_ratio, total_trades, win_rate, total_pnl_pips, profit_factor, score, ...}]
    """
    rows = []
    for pair, info in data.items():
        top5 = info.get("top5", [])
        for i, c in enumerate(top5):
            rows.append({
                "source": "sl_tp_grid",
                "pair": pair,
                "rank": i + 1,
                "sl_pips": c.get("sl_pips"),
                "tp_pips": c.get("tp_pips"),
                "rr_ratio": c.get("rr_ratio"),
                "total_trades": c.get("total_trades", 0),
                "win_rate": c.get("win_rate", 0),
                "total_pnl_pips": c.get("total_pnl_pips", 0),
                "avg_pnl_pips": c.get("avg_pnl_pips", 0),
                "profit_factor": c.get("profit_factor", 0),
                "max_drawdown_pips": c.get("max_drawdown_pips", 0),
                "score": c.get("score", 0),
            })
    return rows


def flatten_rr_grid(data):
    """Transform grid_search_rr_results.json.
    
    Input: {pair: {optimal: {...}, optimal_rr15: {...}, top10: [...]}}
    Output: [{pair, sl_pips, tp_pips, rr_ratio, quality, ...}]
    """
    rows = []
    for pair, info in data.items():
        top10 = info.get("top10", [])
        for i, c in enumerate(top10):
            rows.append({
                "source": "rr_grid",
                "pair": pair,
                "rank": i + 1,
                "sl_pips": c.get("sl_pips"),
                "tp_pips": c.get("tp_pips"),
                "rr_ratio": c.get("rr_ratio"),
                "total_trades": c.get("total_trades", 0),
                "win_rate": c.get("win_rate", 0),
                "total_pnl_pips": c.get("total_pnl_pips", 0),
                "avg_pnl_pips": c.get("avg_pnl_pips", 0),
                "profit_factor": c.get("profit_factor", 0),
                "max_drawdown_pips": c.get("max_drawdown_pips", 0),
                "quality": c.get("quality", 0),
            })
    return rows


def flatten_momentum_grid(data):
    """Transform grid_search_momentum.json.
    
    Input: [{n, wr, pnl, avg, pf, mdd, score, params: {mom, hold, dd, score, session}}]
    Output: [{source, mom, hold, dd, min_score, session, n, wr, pnl, avg, pf, mdd, score}]
    """
    rows = []
    for c in data:
        params = c.get("params", {})
        rows.append({
            "source": "momentum",
            "pair": "PORTFOLIO",
            "mom": params.get("mom"),
            "hold": params.get("hold"),
            "dd": params.get("dd"),
            "min_score": params.get("score"),
            "session": params.get("session", ""),
            "n": c.get("n", 0),
            "wr": c.get("wr", 0),
            "pnl": c.get("pnl", 0),
            "avg": c.get("avg", 0),
            "pf": c.get("pf", 0),
            "mdd": c.get("mdd", 0),
            "score": c.get("score", 0),
        })
    return rows


def flatten_bos_ob_grid(data):
    """Transform optimizer/bot2_bos_ob_grid.json into dashboard-ready format.

    Input: {PAIR: [{params: {bos_lookback, ob_max_age, sl_atr_mult, tp_atr_mult, min_score}, score, trades, win_rate, profit_factor, ...}]}
    Output: [{source, pair, bos_lookback, ob_max_age, sl_atr_mult, tp_atr_mult, min_score, score, trades, wr, pf, ...}]
    """
    rows = []
    for pair, configs in data.items():
        for c in configs:
            params = c.get("params", {})
            rows.append({
                "source": "bos_ob_grid",
                "pair": pair,
                "bos_lookback": params.get("bos_lookback"),
                "ob_max_age": params.get("ob_max_age"),
                "sl_atr_mult": params.get("sl_atr_mult"),
                "tp_atr_mult": params.get("tp_atr_mult"),
                "min_score": params.get("min_score"),
                "score": c.get("score", 0),
                "trades": c.get("trades", 0),
                "wr": c.get("win_rate", 0),
                "pf": c.get("profit_factor", 0),
                "total_pnl": c.get("total_pnl", 0),
                "max_dd_pct": c.get("max_dd_pct", 0),
                "sharpe": c.get("sharpe", 0),
                "passed_gates": c.get("passed_gates", False),
            })
    return rows


def flatten_session_filter(data):
    """Transform optimizer/session_filter_results.json into dashboard-ready format.

    Input: {timestamp, pairs: {PAIR: {session_breakdown: {session: {trades, wr, pf, dd, pnl, sharpe, avg_rr}}}}}
    Output: [{source, pair, session, trades, wr, pf, dd, pnl, sharpe, avg_rr}]
    """
    rows = []
    for pair, info in data.get("pairs", {}).items():
        for session, metrics in info.get("session_breakdown", {}).items():
            rows.append({
                "source": "session_filter",
                "pair": pair,
                "session": session,
                "trades": metrics.get("trades", 0),
                "wr": metrics.get("wr", 0),
                "pf": metrics.get("pf", 0),
                "dd": metrics.get("dd", 0),
                "pnl": metrics.get("pnl", 0),
                "sharpe": metrics.get("sharpe", 0),
                "avg_rr": metrics.get("avg_rr", 0),
            })
    return rows


def build_heatmap_data(rows, x_key, y_key, metric_key, pair_filter=None):
    """Build a 2D heatmap matrix from flat rows.
    
    Returns: {
        x_values: [...],
        y_values: [...],
        matrix: [[metric_value, ...], ...],  # [y_idx][x_idx]
        metric: metric_key,
        pair: pair_filter or "ALL"
    }
    """
    if pair_filter:
        rows = [r for r in rows if r.get("pair") == pair_filter]
    
    x_vals = sorted(set(r.get(x_key) for r in rows if r.get(x_key) is not None))
    y_vals = sorted(set(r.get(y_key) for r in rows if r.get(y_key) is not None))
    
    # Build lookup
    lookup = {}
    for r in rows:
        x = r.get(x_key)
        y = r.get(y_key)
        m = r.get(metric_key)
        if x is not None and y is not None and m is not None:
            key = (x, y)
            # If duplicates, take the one with more trades or higher metric
            if key not in lookup or m > lookup[key]:
                lookup[key] = m
    
    matrix = []
    for y in y_vals:
        row = []
        for x in x_vals:
            row.append(lookup.get((x, y), None))
        matrix.append(row)
    
    return {
        "x_values": x_vals,
        "y_values": y_vals,
        "matrix": matrix,
        "x_key": x_key,
        "y_key": y_key,
        "metric": metric_key,
        "pair": pair_filter or "ALL",
    }


def build_sensitivity_data(rows, param_key, metric_keys, pair_filter=None):
    """Build parameter sensitivity data: aggregate metric by parameter value.
    
    For each value of param_key, compute mean/median of each metric.
    Returns: {param_key, values: [...], metrics: {metric_key: {mean: [...], min: [...], max: [...]}}}
    """
    if pair_filter:
        rows = [r for r in rows if r.get("pair") == pair_filter]
    
    from collections import defaultdict
    groups = defaultdict(lambda: defaultdict(list))
    
    for r in rows:
        pv = r.get(param_key)
        if pv is None:
            continue
        for mk in metric_keys:
            mv = r.get(mk)
            if mv is not None:
                groups[pv][mk].append(mv)
    
    values = sorted(groups.keys())
    metrics = {}
    for mk in metric_keys:
        means = []
        mins = []
        maxs = []
        for v in values:
            vals = groups[v].get(mk, [])
            if vals:
                means.append(round(sum(vals) / len(vals), 2))
                mins.append(round(min(vals), 2))
                maxs.append(round(max(vals), 2))
            else:
                means.append(None)
                mins.append(None)
                maxs.append(None)
        metrics[mk] = {"mean": means, "min": mins, "max": maxs}
    
    return {
        "param_key": param_key,
        "values": values,
        "metrics": metrics,
        "pair": pair_filter or "ALL",
    }


def build_parallel_coords_data(rows, param_keys, metric_key, top_n=50):
    """Build parallel coordinates data.
    
    Returns top_n rows sorted by metric_key, with param_keys as axes.
    """
    sorted_rows = sorted(rows, key=lambda r: r.get(metric_key, 0), reverse=True)[:top_n]
    
    axes = []
    for pk in param_keys:
        vals = [r.get(pk) for r in sorted_rows if r.get(pk) is not None]
        if vals:
            axes.append({
                "key": pk,
                "min": min(vals),
                "max": max(vals),
            })
    
    lines = []
    for r in sorted_rows:
        line = {"metric": r.get(metric_key, 0), "pair": r.get("pair", ""), "values": {}}
        for pk in param_keys:
            v = r.get(pk)
            if v is not None:
                line["values"][pk] = v
        lines.append(line)
    
    return {"axes": axes, "lines": lines, "metric": metric_key}


def flatten_balanced_optimization(data):
    """Transform balanced_optimization.json into top-configs + current comparison.

    Input: {pair: {bars, combos_tested, valid_configs, top_configs: [{params+metrics}], current: {params}}}
    Output: (top_configs_rows, current_configs_dict)
    """
    top_rows = []
    current_configs = {}
    for pair, info in data.items():
        # Current config
        cur = info.get("current", {})
        if cur:
            current_configs[pair] = cur

        # Top configs
        for i, cfg in enumerate(info.get("top_configs", [])):
            row = {
                "source": "balanced_optimization",
                "pair": pair,
                "rank": i + 1,
                "sl_pips": cfg.get("sl_pips"),
                "tp_pips": cfg.get("tp_pips"),
                "rsi_period": cfg.get("rsi_period"),
                "rsi_oversold": cfg.get("rsi_oversold"),
                "rsi_overbought": cfg.get("rsi_overbought"),
                "bb_period": cfg.get("bb_period"),
                "bb_mult": cfg.get("bb_mult"),
                "momentum_threshold": cfg.get("momentum_threshold"),
                "max_hold": cfg.get("max_hold"),
                "direction": cfg.get("direction"),
                "total_trades": cfg.get("total_trades", 0),
                "wins": cfg.get("wins", 0),
                "losses": cfg.get("losses", 0),
                "win_rate": cfg.get("win_rate", 0),
                "total_pnl_pips": cfg.get("total_pnl_pips", 0),
                "avg_pnl_pips": cfg.get("avg_pnl_pips", 0),
                "trades_per_week": cfg.get("trades_per_week", 0),
                "max_drawdown_pips": cfg.get("max_drawdown_pips", 0),
                "profit_factor": cfg.get("profit_factor", 0),
                "rr_ratio": cfg.get("rr_ratio", 0),
                "expectancy": cfg.get("expectancy", 0),
                "score": cfg.get("score", 0),
            }
            top_rows.append(row)
    return top_rows, current_configs


def flatten_walk_forward(data):
    """Transform walk_forward_revived.json into dashboard-ready format.

    Input: {results: [{pair, params, is_*, oos_*, status, reason, ...}]}
    Output: [{pair, params, is: {...}, oos: {...}, status, reason, ...}]
    """
    results = []
    for entry in data.get("results", []):
        is_data = {}
        oos_data = {}
        for k, v in entry.items():
            if k.startswith("is_"):
                is_data[k[3:]] = v
            elif k.startswith("oos_"):
                oos_data[k[4:]] = v
        results.append({
            "pair": entry.get("pair"),
            "params": entry.get("params", {}),
            "total_bars": entry.get("total_bars"),
            "is_bars": entry.get("is_bars"),
            "oos_bars": entry.get("oos_bars"),
            "is": is_data,
            "oos": oos_data,
            "wr_drop_pp": entry.get("wr_drop_pp"),
            "status": entry.get("status"),
            "reason": entry.get("reason"),
        })
    return results


def load_from_sqlite():
    """Load optimization data from SQLite DB and return dashboard-ready components.
    
    Returns: (all_rows, heatmaps, sensitivities, parallel_coords, top_configs,
              current_configs, walk_forward, sources) or None if DB missing/empty.
    """
    if not os.path.exists(DB_PATH):
        print(f"  SQLite DB not found: {DB_PATH}")
        return None
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Check if we have data
    cur.execute("SELECT COUNT(*) FROM grid_results")
    grid_count = cur.fetchone()[0]
    if grid_count == 0:
        print("  SQLite DB has no grid_results")
        conn.close()
        return None
    
    print(f"  SQLite DB: {grid_count} grid_results rows")
    
    all_rows = []
    heatmaps = []
    sensitivities = []
    parallel_coords = []
    top_configs = []
    current_configs = {}
    walk_forward = []
    sources = {}
    
    # ── 1. Grid Results ──────────────────────────────────────────
    # Group by run_id to handle different param sets separately
    cur.execute("SELECT DISTINCT run_id FROM grid_results")
    run_ids = [r[0] for r in cur.fetchall()]
    
    for run_id in run_ids:
        cur.execute("""
            SELECT bot_id, combo_idx, params_json, score, passed_gates,
                   gate_failures, trades, win_rate, profit_factor,
                   sharpe_ratio, avg_rr_ratio, total_pnl, max_dd_pct, sqn
            FROM grid_results WHERE run_id = ?
        """, (run_id,))
        db_rows = cur.fetchall()
        if not db_rows:
            continue
        
        rows = []
        param_keys_set = set()
        for r in db_rows:
            params = json.loads(r["params_json"])
            if not isinstance(params, dict):
                continue  # skip non-dict params (e.g. lists)
            param_keys_set.update(params.keys())
            row = {
                "source": f"grid_{run_id}",
                "pair": f"Bot #{r['bot_id']}",
                "run_id": run_id,
                "bot_id": r["bot_id"],
                "combo_idx": r["combo_idx"],
                "score": r["score"] or 0,
                "passed_gates": bool(r["passed_gates"]),
                "trades": r["trades"] or 0,
                "win_rate": r["win_rate"] or 0,
                "profit_factor": r["profit_factor"] or 0,
                "sharpe_ratio": r["sharpe_ratio"] or 0,
                "avg_rr_ratio": r["avg_rr_ratio"] or 0,
                "total_pnl": r["total_pnl"] or 0,
                "max_dd_pct": r["max_dd_pct"] or 0,
                "sqn": r["sqn"] or 0,
            }
            # Expand params into top-level keys
            for k, v in params.items():
                row[k] = v
            rows.append(row)
        
        all_rows.extend(rows)
        param_keys = sorted(param_keys_set)
        
        # Determine a short label for this run
        run_label = run_id.replace("opt_", "").replace("st_opt_", "st_")
        source_key = f"grid_{run_id}"
        sources[source_key] = {
            "count": len(rows),
            "run_id": run_id,
            "params": param_keys,
        }
        print(f"    {source_key}: {len(rows)} configs, params={param_keys}")
        
        # Build heatmaps: pair up param keys for 2D matrices
        numeric_params = []
        for pk in param_keys:
            vals = [r.get(pk) for r in rows if r.get(pk) is not None]
            if vals and all(isinstance(v, (int, float)) for v in vals):
                numeric_params.append(pk)
        
        # Generate heatmaps for all 2-combinations of numeric params
        for metric in ["score", "total_pnl", "win_rate", "profit_factor"]:
            for xk, yk in itertools.combinations(numeric_params, 2):
                hm = build_heatmap_data(rows, xk, yk, metric)
                if hm["matrix"] and any(any(v is not None for v in row) for row in hm["matrix"]):
                    hm["title"] = f"Bot #{rows[0]['bot_id']}: {xk} vs {yk} ({metric})"
                    hm["source"] = source_key
                    heatmaps.append(hm)
        
        # Sensitivity: each param vs key metrics
        for pk in numeric_params:
            s = build_sensitivity_data(rows, pk, ["score", "total_pnl", "win_rate", "profit_factor"])
            s["title"] = f"Bot #{rows[0]['bot_id']}: {pk} sensitivity"
            s["source"] = source_key
            sensitivities.append(s)
        
        # Parallel coords (top 50 by score)
        if len(numeric_params) >= 2:
            pc = build_parallel_coords_data(rows, numeric_params, "score", 50)
            pc["title"] = f"Bot #{rows[0]['bot_id']}: Top 50 Configs ({run_label})"
            pc["source"] = source_key
            parallel_coords.append(pc)
    
    # ── 2. Best Params (top_configs) ─────────────────────────────
    cur.execute("""
        SELECT bot_id, params_json, score, wf_passed, trades, win_rate,
               profit_factor, total_pnl, max_dd_pct, notes, run_id
        FROM best_params ORDER BY score DESC
    """)
    for r in cur.fetchall():
        params = json.loads(r["params_json"])
        # Skip broken entries (non-dict params or absurd scores)
        if not isinstance(params, dict):
            continue
        score = r["score"] or 0
        if score <= -999999:
            continue
        param_summary = ", ".join(f"{k}={v}" for k, v in params.items())
        cfg = {
            "source": "best_params",
            "pair": f"Bot #{r['bot_id']}",
            "param_summary": param_summary[:80],
            "bot_id": r["bot_id"],
            "run_id": r["run_id"],
            "rank": len(top_configs) + 1,
            "score": r["score"] or 0,
            "wf_passed": bool(r["wf_passed"]),
            "trades": r["trades"] or 0,
            "win_rate": r["win_rate"] or 0,
            "profit_factor": r["profit_factor"] or 0,
            "total_pnl": r["total_pnl"] or 0,
            "max_dd_pct": r["max_dd_pct"] or 0,
            "notes": r["notes"] or "",
        }
        cfg.update(params)
        top_configs.append(cfg)
    
    sources["best_params"] = {"count": len(top_configs)}
    print(f"    best_params: {len(top_configs)} configs")
    
    # ── 3. Walk-Forward Results ──────────────────────────────────
    cur.execute("""
        SELECT bot_id, config_idx, params_json, wf_passed, profitable_splits,
               total_splits, decay_detected, decay_ratio, stability_json,
               splits_json, score, run_id
        FROM wf_results ORDER BY score DESC
    """)
    for r in cur.fetchall():
        params = json.loads(r["params_json"])
        stability = json.loads(r["stability_json"]) if r["stability_json"] else {}
        splits = json.loads(r["splits_json"]) if r["splits_json"] else []
        
        # Determine status
        if r["wf_passed"]:
            status = "PASS"
        elif r["profitable_splits"] and r["total_splits"] and r["profitable_splits"] / max(r["total_splits"], 1) >= 0.5:
            status = "WARN"
        else:
            status = "FAIL"
        
        # Build IS/OOS metrics from splits
        is_metrics = {}
        oos_metrics = {}
        for sp in splits:
            for prefix, target in [("train", is_metrics), ("test", oos_metrics)]:
                for key in ["trades", "win_rate", "profit_factor", "total_pnl", "max_dd_pct", "sharpe"]:
                    sp_key = f"{prefix}_{key}" if f"{prefix}_{key}" in sp else key
                    if sp_key in sp:
                        target.setdefault(key, []).append(sp[sp_key])
        
        # Aggregate
        def agg_metrics(metrics_dict):
            result = {}
            for k, vals in metrics_dict.items():
                if vals:
                    result[k] = round(sum(vals) / len(vals), 2)
            return result
        
        # Build param summary for display
        param_summary = ", ".join(f"{k}={v}" for k, v in params.items() if isinstance(v, (int, float, str)))
        wf_entry = {
            "pair": f"Config #{r['config_idx']+1}",
            "param_summary": param_summary[:80],
            "config_idx": r["config_idx"],
            "params": params,
            "status": status,
            "wf_passed": bool(r["wf_passed"]),
            "profitable_splits": r["profitable_splits"] or 0,
            "total_splits": r["total_splits"] or 0,
            "decay_detected": bool(r["decay_detected"]),
            "decay_ratio": r["decay_ratio"] or 0,
            "score": r["score"] or 0,
            "is": agg_metrics(is_metrics),
            "oos": agg_metrics(oos_metrics),
            "stability": stability,
            "splits": splits,
            "run_id": r["run_id"],
        }
        walk_forward.append(wf_entry)
    
    sources["walk_forward"] = {"count": len(walk_forward)}
    print(f"    walk_forward: {len(walk_forward)} configs")
    
    # Pairs list
    pairs = sorted(set(r.get("pair", "") for r in all_rows if r.get("pair")))
    
    # Bots list (from grid_results when no real pair column exists)
    bots = sorted(set(r.get("pair", "") for r in all_rows if r.get("pair", "").startswith("Bot #")))
    
    conn.close()
    
    return (all_rows, heatmaps, sensitivities, parallel_coords,
            top_configs, current_configs, walk_forward, sources, pairs, bots)


def main():
    print("=" * 60)
    print("Optimization Dashboard Builder")
    print("=" * 60)

    all_rows = []
    heatmaps = []
    sensitivities = []
    parallel_coords = []
    top_configs = []
    current_configs = {}
    walk_forward = []
    sources = {}
    pairs = []
    
    # ── Try SQLite first (PRIMARY source) ────────────────────────
    print("\n  Loading from SQLite...")
    sqlite_result = load_from_sqlite()
    
    if sqlite_result is not None:
        (all_rows, heatmaps, sensitivities, parallel_coords,
         top_configs, current_configs, walk_forward, sources, pairs, bots) = sqlite_result
        print(f"\n  ✓ SQLite loaded: {len(all_rows)} grid rows, {len(top_configs)} top configs, {len(walk_forward)} WF configs")
    else:
        # ── Fallback to JSON files ────────────────────────────────
        print("  Falling back to JSON files...")
        bots = []
    
        # 1. Bot #2 EMA+ADX Grid
        bot2 = load_json(os.path.join(DATA_DIR, "bot2_grid_results.json"))
        if bot2:
            rows = flatten_bot2_grid(bot2)
            all_rows.extend(rows)
            sources["bot2_ema_adx"] = {"count": len(rows), "pairs": list(bot2.get("all_results", {}).keys())}
            print(f"  bot2_grid: {len(rows)} configs")
            
            # Heatmaps: fast vs slow for each pair, metric=total_pips
            for pair in bot2.get("all_results", {}).keys():
                hm = build_heatmap_data(rows, "fast", "slow", "total_pips", pair)
                if hm["matrix"]:
                    hm["title"] = f"{pair}: EMA Fast vs Slow (Total Pips)"
                    heatmaps.append(hm)
            
            # Heatmap: sl vs tp aggregated
            hm = build_heatmap_data(rows, "sl", "tp", "total_pips")
            hm["title"] = "All Pairs: SL vs TP (Total Pips)"
            heatmaps.append(hm)
            
            # Sensitivity: each param vs total_pips
            for param in ["fast", "slow", "adx", "sl", "tp"]:
                s = build_sensitivity_data(rows, param, ["total_pips", "wr", "pf"])
                s["title"] = f"EMA+ADX: {param} sensitivity"
                sensitivities.append(s)
            
            # Parallel coords
            pc = build_parallel_coords_data(rows, ["fast", "slow", "adx", "sl", "tp"], "total_pips", 30)
            pc["title"] = "EMA+ADX: Top 30 Configs (Parallel Coordinates)"
            parallel_coords.append(pc)
        
        # 2. Portfolio Grid
        portfolio = load_json(os.path.join(DATA_DIR, "portfolio_grid_search.json"))
        if portfolio:
            rows = flatten_portfolio_grid(portfolio)
            all_rows.extend(rows)
            sources["portfolio"] = {"count": len(rows)}
            print(f"  portfolio_grid: {len(rows)} configs")
            
            hm = build_heatmap_data(rows, "max_positions", "risk_pct", "return_pct")
            hm["title"] = "Portfolio: Positions vs Risk (Return %)"
            heatmaps.append(hm)
            
            hm2 = build_heatmap_data(rows, "max_positions", "risk_pct", "max_dd_pct")
            hm2["title"] = "Portfolio: Positions vs Risk (Max DD %)"
            heatmaps.append(hm2)
        
        # 3. Grid Optimize V2
        gov2 = load_json(os.path.join(DATA_DIR, "grid_optimize_v2_results.json"))
        if gov2:
            rows = flatten_grid_optimize_v2(gov2)
            all_rows.extend(rows)
            sources["grid_optimize_v2"] = {"count": len(rows), "pairs": list(gov2.keys())}
            print(f"  grid_optimize_v2: {len(rows)} pairs")
            
            # Heatmaps for param pairs
            param_keys = [k for k in rows[0].keys() if k.startswith("param_")] if rows else []
            if len(param_keys) >= 2 and len(rows) > 1:
                pc = build_parallel_coords_data(
                    rows, param_keys, "combined_quality", len(rows)
                )
                pc["title"] = "Grid Optimize V2: Best Params per Pair"
                parallel_coords.append(pc)
                
                for pk in param_keys[:5]:
                    s = build_sensitivity_data(rows, pk, ["combined_quality", "is_pnl", "oos_pnl"])
                    s["title"] = f"V2: {pk.replace('param_', '')} vs Quality"
                    sensitivities.append(s)
        
        # 4. SL/TP Grid
        sltp = load_json(os.path.join(DATA_DIR, "grid_search_results.json"))
        if sltp:
            rows = flatten_sl_tp_grid(sltp)
            all_rows.extend(rows)
            sources["sl_tp_grid"] = {"count": len(rows), "pairs": list(sltp.keys())}
            print(f"  sl_tp_grid: {len(rows)} configs")
            
            for pair in list(sltp.keys())[:5]:
                pair_rows = [r for r in rows if r["pair"] == pair]
                if pair_rows:
                    hm = build_heatmap_data(pair_rows, "sl_pips", "tp_pips", "total_pnl_pips")
                    hm["title"] = f"{pair}: SL vs TP (PnL Pips)"
                    heatmaps.append(hm)
        
        # 5. RR Grid
        rr = load_json(os.path.join(DATA_DIR, "grid_search_rr_results.json"))
        if rr:
            rows = flatten_rr_grid(rr)
            all_rows.extend(rows)
            sources["rr_grid"] = {"count": len(rows), "pairs": list(rr.keys())}
            print(f"  rr_grid: {len(rows)} configs")
            
            s = build_sensitivity_data(rows, "rr_ratio", ["total_pnl_pips", "quality"])
            s["title"] = "Risk-Reward Ratio Sensitivity"
            sensitivities.append(s)
        
        # 6. Momentum Grid
        mom = load_json(os.path.join(DATA_DIR, "grid_search_momentum.json"))
        if mom:
            rows = flatten_momentum_grid(mom)
            all_rows.extend(rows)
            sources["momentum"] = {"count": len(rows)}
            print(f"  momentum_grid: {len(rows)} configs")
            
            hm = build_heatmap_data(rows, "mom", "hold", "score")
            hm["title"] = "Momentum: Mom vs Hold (Score)"
            heatmaps.append(hm)
        
        # 7. Grid Optimize V1
        gov1 = load_json(os.path.join(DATA_DIR, "grid_optimize_results.json"))
        if gov1:
            rows = flatten_grid_optimize_v2(gov1)
            if rows:
                all_rows.extend(rows)
                sources["grid_optimize_v1"] = {"count": len(rows)}
                print(f"  grid_optimize_v1: {len(rows)} pairs")
        
        # 8. Balanced Optimization
        balanced = load_json(os.path.join(DATA_DIR, "balanced_optimization.json"))
        if balanced:
            top_rows, cur_configs = flatten_balanced_optimization(balanced)
            top_configs = top_rows
            current_configs = cur_configs
            all_rows.extend(top_rows)
            sources["balanced_optimization"] = {"count": len(top_rows), "pairs": list(balanced.keys())}
            print(f"  balanced_optimization: {len(top_rows)} top configs, {len(cur_configs)} current configs")

        # 9. Walk-Forward data
        wf_data = load_json(os.path.join(DATA_DIR, "walk_forward_revived.json"))
        if wf_data:
            walk_forward = flatten_walk_forward(wf_data)
            sources["walk_forward"] = {"count": len(walk_forward), "method": wf_data.get("method", "")}
            print(f"  walk_forward: {len(walk_forward)} pairs")

        # 10. BOS+OB Grid (new optimizer)
        OPTIMIZER_DIR = os.path.join(DATA_DIR, "optimizer")
        bos_ob = load_json(os.path.join(OPTIMIZER_DIR, "bot2_bos_ob_grid.json"))
        if bos_ob:
            rows = flatten_bos_ob_grid(bos_ob)
            all_rows.extend(rows)
            sources["bos_ob_grid"] = {"count": len(rows), "pairs": list(bos_ob.keys())}
            print(f"  bos_ob_grid: {len(rows)} configs")

            for pair in list(bos_ob.keys())[:5]:
                pair_rows = [r for r in rows if r["pair"] == pair]
                if pair_rows:
                    hm = build_heatmap_data(pair_rows, "bos_lookback", "sl_atr_mult", "score")
                    hm["title"] = f"{pair}: BOS Lookback vs SL (Score)"
                    heatmaps.append(hm)

            for param in ["bos_lookback", "ob_max_age", "sl_atr_mult", "tp_atr_mult", "min_score"]:
                s = build_sensitivity_data(rows, param, ["score", "wr", "pf"])
                s["title"] = f"BOS+OB: {param} sensitivity"
                sensitivities.append(s)

        # 11. Session Filter (new optimizer)
        sess_filter = load_json(os.path.join(OPTIMIZER_DIR, "session_filter_results.json"))
        if sess_filter:
            rows = flatten_session_filter(sess_filter)
            all_rows.extend(rows)
            sources["session_filter"] = {"count": len(rows), "pairs": list(sess_filter.get("pairs", {}).keys())}
            print(f"  session_filter: {len(rows)} entries")

            if rows:
                hm = build_heatmap_data(rows, "pair", "session", "pnl")
                hm["title"] = "Session Filter: Pair vs Session (PnL)"
                heatmaps.append(hm)

    # Deduplicate heatmaps: group by (x_key, y_key, metric) and keep best
    def _dedup_heatmaps(hms, max_count=20):
        """Keep at most max_count heatmaps, preferring those with more data."""
        from collections import defaultdict
        groups = defaultdict(list)
        for hm in hms:
            key = (hm.get("x_key"), hm.get("y_key"), hm.get("metric"))
            groups[key].append(hm)
        # For each group, keep the one with the most matrix cells
        best = []
        for key, items in groups.items():
            items.sort(key=lambda h: len(h.get("x_values", [])) * len(h.get("y_values", [])), reverse=True)
            best.append(items[0])
        # Sort by data density (more cells = more useful), then limit
        best.sort(key=lambda h: len(h.get("x_values", [])) * len(h.get("y_values", [])), reverse=True)
        return best[:max_count]

    heatmaps = _dedup_heatmaps(heatmaps)

    # Build output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_configs": len(all_rows),
        "sources": sources,
        "heatmaps": heatmaps,
        "sensitivities": sensitivities,
        "parallel_coords": parallel_coords,
        "top_configs": top_configs,
        "current_configs": current_configs,
        "walk_forward": walk_forward,
        "pairs": sorted(set(r.get("pair", "") for r in all_rows if r.get("pair") and not r.get("pair", "").startswith("Bot #"))),
        "bots": bots,
        "raw_samples": {
            "bot2": [r for r in all_rows if r.get("source") == "bot2_ema_adx"][:5],
            "portfolio": [r for r in all_rows if r.get("source") == "portfolio"][:3],
            "sl_tp": [r for r in all_rows if r.get("source") == "sl_tp_grid"][:5],
            "bos_ob": [r for r in all_rows if r.get("source") == "bos_ob_grid"][:5],
            "session_filter": [r for r in all_rows if r.get("source") == "session_filter"][:5],
        },
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    
    print(f"\n  Output: {OUTPUT_FILE}")
    print(f"  Total configs: {len(all_rows)}")
    print(f"  Heatmaps: {len(heatmaps)}")
    print(f"  Sensitivity charts: {len(sensitivities)}")
    print(f"  Parallel coord charts: {len(parallel_coords)}")
    print(f"  Top configs: {len(top_configs)}")
    print(f"  Current configs: {len(current_configs)} pairs")
    print(f"  Walk-forward: {len(walk_forward)} pairs")
    print(f"  Pairs: {len(output['pairs'])}")
    print("=" * 60)


if __name__ == "__main__":
    main()
