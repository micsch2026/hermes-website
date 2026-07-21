#!/usr/bin/env python3
"""
build_data_status.py — Data Pipeline Status Builder.

Scans all data directories, computes quality metrics, detects gaps,
and generates pipeline_status.json for the Data Pipeline page.

Output: /root/.hermes/site/api/data/pipeline_status.json

Run via cron or manually: python3 build_data_status.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Timeframe Config (single source of truth) ──────────────────────
# Each entry: directory, file suffix, max_age_hours, expected_gap_hours, weekend_gap_hours
TIMEFRAMES = {
    "m15": {
        "dir": "/root/trading/data/history_m15",
        "suffix": "_m15.json",
        "max_age_hours": 18,        # 15min bars — FX closes ~17-18 UTC, reopen ~22 UTC
        "expected_gap_hours": 0.25,
        "weekend_gap_hours": 72,    # same weekend tolerance as 1h
    },
    "1h": {
        "dir": "/root/trading/data/history_1h",
        "suffix": "_1h.json",
        "max_age_hours": 2.5,
        "expected_gap_hours": 1,
        "weekend_gap_hours": 72,
    },
    "4h": {
        "dir": "/root/trading/data/history_4h",
        "suffix": "_4h.json",
        "max_age_hours": 10,
        "expected_gap_hours": 4,
        "weekend_gap_hours": 96,
    },
    "1d": {
        "dir": "/root/trading/data/history_1d",
        "suffix": "_1d.json",
        "max_age_hours": 30,
        "expected_gap_hours": 24,
        "weekend_gap_hours": 168,
    },
}

# Display order for the frontend (matches table columns)
TF_ORDER = ["m15", "1h", "4h", "1d"]

# ── Other Paths ────────────────────────────────────────────────────
FETCH_LOG = "/root/fx-bot/logs/fetch.log"
FX_DASHBOARD = "/root/.hermes/site/api/fx/dashboard.json"
OUTPUT = "/root/.hermes/site/api/data/pipeline_status.json"
ASSETS_TOML = "/root/fx-bot/config/assets.toml"
BOT2_ASSETS_TOML = "/root/fx-bot/config/bot2_m15_mr.toml"


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _scan_bars(directory, suffix, tf_cfg):
    """Scan all bar files in a directory and compute quality metrics."""
    results = {}
    if not os.path.isdir(directory):
        return results

    now = datetime.now(timezone.utc)
    max_age = tf_cfg["max_age_hours"]
    weekend_limit_secs = tf_cfg["weekend_gap_hours"] * 3600

    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        symbol = fname.replace(suffix, "")
        path = os.path.join(directory, fname)

        try:
            with open(path) as f:
                data = json.load(f)
            bars = data.get("bars", data) if isinstance(data, dict) else data
        except Exception:
            results[symbol] = {
                "bars": 0, "first_ts": None, "last_ts": None,
                "first_date": "", "last_date": "", "age_hours": None,
                "gaps": 0, "max_gap_hours": 0,
                "file_size_kb": round(os.path.getsize(path) / 1024, 1),
                "status": "ERROR", "error": "parse_failed", "quality_score": 0,
            }
            continue

        if not bars:
            results[symbol] = {
                "bars": 0, "first_ts": None, "last_ts": None,
                "first_date": "", "last_date": "", "age_hours": None,
                "gaps": 0, "max_gap_hours": 0,
                "file_size_kb": round(os.path.getsize(path) / 1024, 1),
                "status": "EMPTY", "quality_score": 0,
            }
            continue

        first_ts = bars[0]["timestamp"]
        last_ts = bars[-1]["timestamp"]
        first_dt = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        raw_age_hours = (now - last_dt).total_seconds() / 3600
        age_hours = _weekend_adjusted_age_hours(raw_age_hours, last_dt, now, tf_cfg)

        # Gap detection
        gaps = 0
        max_gap = 0
        gap_ranges = []

        for i in range(1, len(bars)):
            diff = bars[i]["timestamp"] - bars[i - 1]["timestamp"]
            if diff > weekend_limit_secs:
                gaps += 1
                gap_hours = diff / 3600
                max_gap = max(max_gap, gap_hours)
                gap_ranges.append({
                    "from": datetime.fromtimestamp(bars[i - 1]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "to": datetime.fromtimestamp(bars[i]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "hours": round(gap_hours, 1),
                })

        # Status determination
        if age_hours <= max_age and gaps == 0:
            status = "OK"
        elif age_hours <= max_age and gaps < 5:
            status = "WARN"
        elif age_hours <= max_age * 4:
            status = "WARN"
        else:
            status = "STALE"

        # Quality Score (0-100): freshness 50pts, gaps 30pts, bar count 20pts
        freshness = max(0, 50 * (1 - age_hours / (max_age * 4)))
        gap_score = max(0, 30 - gaps * 5)
        bar_score = min(20, len(bars) / 10)
        quality_score = round(freshness + gap_score + bar_score)

        results[symbol] = {
            "bars": len(bars),
            "first_ts": first_ts,
            "last_ts": last_ts,
            "first_date": first_dt.strftime("%Y-%m-%d"),
            "last_date": last_dt.strftime("%Y-%m-%d %H:%M"),
            "age_hours": round(age_hours, 1),
            "raw_age_hours": round(raw_age_hours, 1),
            "gaps": gaps,
            "max_gap_hours": round(max_gap, 1) if max_gap > 0 else 0,
            "gap_ranges": gap_ranges[:5],
            "file_size_kb": round(os.path.getsize(path) / 1024, 1),
            "status": status,
            "quality_score": quality_score,
        }

    return results


def _weekend_adjusted_age_hours(raw_age_hours, last_dt, now, tf_cfg):
    """Subtract closed-market weekend hours from age for FX/Stocks/Indices."""
    if now.weekday() not in (5, 6):
        return raw_age_hours

    # For higher timeframes, any bar from the current weekend is current
    tf_label = tf_cfg.get("_label", "1h")
    if tf_label in ("4h", "1d") and last_dt.weekday() in (4, 5, 6) and raw_age_hours < 72:
        return 0.0

    friday_close = last_dt.replace(hour=21, minute=0, second=0, microsecond=0)
    if last_dt.weekday() == 5:
        friday_close = (last_dt - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
    elif last_dt.weekday() == 6:
        friday_close = (last_dt - timedelta(days=2)).replace(hour=21, minute=0, second=0, microsecond=0)

    sunday_open = friday_close + timedelta(days=2, hours=1)

    if last_dt < friday_close:
        if now < sunday_open:
            return max(0, (friday_close - last_dt).total_seconds() / 3600)
        else:
            weekend_hours = (sunday_open - friday_close).total_seconds() / 3600
            return max(0, raw_age_hours - weekend_hours)
    elif friday_close <= last_dt < sunday_open:
        if now < sunday_open:
            return 0.0
        else:
            return max(0, (now - sunday_open).total_seconds() / 3600)
    else:
        return raw_age_hours


def _parse_fetch_log(log_path, max_lines=200):
    """Parse fetch.log for recent fetch events."""
    events = []
    if not os.path.exists(log_path):
        return events

    try:
        with open(log_path) as f:
            lines = f.readlines()
    except Exception:
        return events

    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue

        entry = {"raw": line}

        if line.startswith("[") and "]" in line:
            ts_str = line[1:line.index("]")]
            entry["time"] = ts_str

        if "bars" in line and ("(" in line or "→" in line or "\u2192" in line):
            bracket_end = line.index("]") + 1 if "]" in line else 0
            rest = line[bracket_end:].strip()
            parts = rest.split(":", 1)
            if len(parts) >= 2:
                symbol = parts[0].strip()
                if symbol:
                    entry["type"] = "fetch_ok"
                    entry["symbol"] = symbol
        elif "Disconnected" in line or "ConnectionLost" in line:
            entry["type"] = "disconnect"
        elif "error" in line.lower() or "fail" in line.lower():
            entry["type"] = "error"
        elif "timeout" in line.lower():
            entry["type"] = "timeout"
        else:
            entry["type"] = "info"

        events.append(entry)

    return events


def _compute_summary(all_data):
    """Compute top-level summary stats."""
    total_assets = 0
    ok_count = 0
    warn_count = 0
    stale_count = 0
    error_count = 0
    total_bars = 0

    for tf, assets in all_data.items():
        for symbol, info in assets.items():
            total_assets += 1
            total_bars += info.get("bars", 0)
            s = info.get("status", "UNKNOWN")
            if s == "OK":
                ok_count += 1
            elif s == "WARN":
                warn_count += 1
            elif s == "STALE":
                stale_count += 1
            else:
                error_count += 1

    healthy = ok_count + warn_count
    health_pct = round(healthy / total_assets * 100, 1) if total_assets > 0 else 0

    return {
        "total_assets": total_assets,
        "total_bars": total_bars,
        "ok": ok_count,
        "warn": warn_count,
        "stale": stale_count,
        "error": error_count,
        "health_pct": health_pct,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def _get_asset_type(symbol):
    """Classify asset as FX, Stock, Index, Commodity."""
    fx_majors = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"}
    indices = {"DE40", "NAS100", "US30", "US500", "UK100", "JP225", "AUS200", "CN50", "FRA40", "HK50", "US2000"}
    commodities = {"XAUUSD", "XAGUSD", "XAUEUR"}

    if symbol in fx_majors:
        return "FX Major"
    if symbol in indices:
        return "Index"
    if symbol in commodities:
        return "Commodity"
    if len(symbol) == 6 and symbol[:3] in {"EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF", "JPY"}:
        return "FX Cross"
    return "Stock"


def _get_active_pairs():
    """Get list of pairs active in any FX bot from config files."""
    import tomllib
    active = set()
    for toml_path in [ASSETS_TOML, BOT2_ASSETS_TOML]:
        try:
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            for section, vals in config.items():
                if section == "DEFAULT":
                    continue
                if isinstance(vals, dict) and vals.get("enabled", True):
                    direction = vals.get("direction", "both")
                    if direction != "none":
                        active.add(section)
        except Exception:
            pass
    return sorted(active)


def build():
    """Main build function."""
    # Scan all timeframes from config
    all_data = {}
    for tf_key in TF_ORDER:
        tf_cfg = TIMEFRAMES[tf_key]
        tf_cfg["_label"] = tf_key  # for weekend adjustment
        print(f"[build_data_status] Scanning {tf_key.upper()} data...")
        all_data[tf_key] = _scan_bars(tf_cfg["dir"], tf_cfg["suffix"], tf_cfg)

    # Collect all unique symbols
    all_symbols = sorted(set().union(*(d.keys() for d in all_data.values())))

    # Build per-asset multi-TF view
    missing_tpl = {"bars": 0, "status": "MISSING", "quality_score": 0}
    assets = []
    for symbol in all_symbols:
        asset_type = _get_asset_type(symbol)
        asset_info = {"symbol": symbol, "type": asset_type}

        # Populate each TF from config
        tf_statuses = []
        tf_scores = []
        for tf_key in TF_ORDER:
            tf_data = all_data[tf_key].get(symbol, missing_tpl)
            asset_info[tf_key] = tf_data
            tf_statuses.append(tf_data.get("status", "MISSING"))
            tf_scores.append(tf_data.get("quality_score", 0))

        # Overall status = worst of all TFs
        if "ERROR" in tf_statuses or "EMPTY" in tf_statuses:
            asset_info["status"] = "ERROR"
        elif "STALE" in tf_statuses:
            asset_info["status"] = "STALE"
        elif "WARN" in tf_statuses:
            asset_info["status"] = "WARN"
        elif "MISSING" in tf_statuses:
            asset_info["status"] = "MISSING"
        else:
            asset_info["status"] = "OK"

        # Overall quality = average of available TF quality scores
        asset_info["quality_score"] = round(sum(tf_scores) / len(tf_scores)) if tf_scores else 0

        assets.append(asset_info)

    # Parse fetch log
    fetch_events = _parse_fetch_log(FETCH_LOG)

    # Get active pairs
    active_pairs = _get_active_pairs()

    # Compute summaries
    summary = _compute_summary(all_data)
    summary["unique_symbols"] = len(all_symbols)
    summary["fx_active_pairs"] = len(active_pairs)
    summary["timeframes"] = {tf: {"count": len(all_data[tf])} for tf in TF_ORDER}
    summary["tf_order"] = TF_ORDER  # tell frontend the column order

    # Build fetch status summary
    last_fetch_ok = None
    last_fetch_error = None
    fetch_ok_count = 0
    fetch_error_count = 0
    for evt in reversed(fetch_events):
        if evt.get("type") == "fetch_ok" and last_fetch_ok is None:
            last_fetch_ok = evt.get("time", "")
        elif evt.get("type") in ("error", "disconnect", "timeout"):
            fetch_error_count += 1
            if last_fetch_error is None:
                last_fetch_error = evt.get("time", "")
        if evt.get("type") == "fetch_ok":
            fetch_ok_count += 1

    fetch_status = {
        "last_success": last_fetch_ok,
        "last_error": last_fetch_error,
        "recent_ok_count": fetch_ok_count,
        "recent_error_count": fetch_error_count,
        "timer_active": True,
    }

    # Compute average quality across all assets
    all_quality = [a.get("quality_score", 0) for a in assets]
    avg_quality = round(sum(all_quality) / len(all_quality)) if all_quality else 0
    summary["avg_quality"] = avg_quality

    # Fetch success rate
    total_fetches = fetch_status["recent_ok_count"] + fetch_status["recent_error_count"]
    fetch_status["success_rate"] = round(fetch_status["recent_ok_count"] / total_fetches * 100, 1) if total_fetches > 0 else 0

    output = {
        "summary": summary,
        "fetch_status": fetch_status,
        "active_pairs": active_pairs,
        "assets": assets,
        "recent_events": [e for e in fetch_events if e.get("type") != "info"][-30:],
    }

    # Write output
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"[build_data_status] Written to {OUTPUT}")
    print(f"[build_data_status] Summary: {summary['total_assets']} assets, "
          f"{summary['ok']} OK, {summary['warn']} WARN, {summary['stale']} STALE, "
          f"{summary['error']} ERROR, health={summary['health_pct']}%")

    return output


if __name__ == "__main__":
    build()
