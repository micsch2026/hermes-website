#!/usr/bin/env python3
"""
Build Backtest API — Scans all backtest JSON files from fx-bot/data/ and
generates a unified API at /root/.hermes/site/api/backtest/.

Outputs:
  - api/backtest/index.json   — list of all backtest runs with summary metrics
  - api/backtest/<id>.json    — full detail for each backtest run

Supports:
  - v2 reports (existing format)
  - v3 reports (BACKTEST_V3_ARCHITECTURE.md schema)
  - Legacy combined/realistic/variant/bot2/deep formats
"""
import json, os, glob, hashlib, sys
from datetime import datetime, timezone

DATA_DIR = '/root/fx-bot/data'
BACKTEST_V2_DIR = '/root/fx-bot/data/backtest_v2'
BACKTEST_V3_DIR = '/root/fx-bot/data/backtest_v3'
API_DIR = '/root/.hermes/site/api/backtest'

# Status thresholds
def classify_status(metrics):
    """Return PASS / WARN / FAIL based on key metrics."""
    wr = metrics.get('win_rate_pct', metrics.get('win_rate', 0)) or 0
    pf = metrics.get('profit_factor', 0) or 0
    dd = metrics.get('max_dd_pct', metrics.get('max_drawdown_pct', 0)) or 0
    pnl = metrics.get('total_pnl', metrics.get('total_pnl_eur', 0)) or 0

    # FAIL conditions
    if pf < 1.0 and pnl < 0:
        return 'FAIL'
    if dd > 25:
        return 'FAIL'

    # WARN conditions
    if wr < 45:
        return 'WARN'
    if dd > 15:
        return 'WARN'
    if pf < 1.2:
        return 'WARN'

    return 'PASS'


def make_id(filename):
    """Generate a stable short ID from filename."""
    h = hashlib.md5(filename.encode()).hexdigest()[:8]
    return f'bt_{h}'


def extract_combined_report(data, filename):
    """Extract from combined_backtest_report.json."""
    summary = data.get('summary', {})
    per_bot = data.get('per_bot', {})
    config = data.get('config', {})
    trades = data.get('trades', [])
    monthly = data.get('monthly', {})
    daily_pnl = data.get('daily_pnl', {})

    # Extract equity curve from daily PnL
    equity_curve = []
    running = config.get('initial_equity', 10000)
    for date in sorted(daily_pnl.keys()):
        running += daily_pnl[date]
        equity_curve.append({'date': date, 'equity': round(running, 2)})

    # Extract drawdown curve
    dd_curve = []
    peak = 0
    for pt in equity_curve:
        peak = max(peak, pt['equity'])
        dd_pct = ((peak - pt['equity']) / peak * 100) if peak > 0 else 0
        dd_curve.append({'date': pt['date'], 'drawdown_pct': round(dd_pct, 2)})

    result = {
        'id': make_id(filename),
        'filename': filename,
        'name': 'Combined Portfolio Backtest',
        'strategy': 'Multi-Bot (RSI+BB MeanRev + EMA+ADX Trend)',
        'generated_at': data.get('generated_at', ''),
        'type': 'portfolio',
        'status': classify_status(summary),
        'summary': {
            'total_trades': summary.get('total_trades', 0),
            'wins': summary.get('wins', 0),
            'losses': summary.get('losses', 0),
            'win_rate_pct': summary.get('win_rate_pct', 0),
            'profit_factor': summary.get('profit_factor', 0),
            'total_pnl_eur': summary.get('total_pnl_eur', 0),
            'max_dd_pct': summary.get('max_dd_pct', 0),
            'sharpe': summary.get('sharpe', 0),
            'recovery_factor': summary.get('recovery_factor', 0),
            'total_days': summary.get('total_days', 0),
            'trades_per_day': summary.get('trades_per_day', 0),
        },
        'per_bot': {
            k: {
                'name': v.get('name', k),
                'trades': v.get('trades', 0),
                'wins': v.get('wins', 0),
                'losses': v.get('losses', 0),
                'win_rate_pct': v.get('win_rate_pct', 0),
                'profit_factor': v.get('profit_factor', 0),
                'total_pnl_eur': v.get('total_pnl_eur', 0),
            }
            for k, v in per_bot.items()
        },
        'config': config,
        'monthly': monthly,
        'equity_curve': equity_curve,
        'drawdown_curve': dd_curve,
        'execution_costs': data.get('execution_costs', {}),
        'margin': data.get('margin', {}),
        'trades': trades[:500],  # limit for API size
        'total_trade_count': len(trades),
        'pairs': data.get('bot1_pairs', []) + data.get('bot2_pairs', []),
        'per_pair': data.get('per_pair', {}),
    }
    return result


def extract_realistic_backtest(data, filename):
    """Extract from realistic_backtest_report.json."""
    metrics = data.get('metrics', {})
    config = data.get('config', {})
    oos = data.get('oos_validation', [])

    result = {
        'id': make_id(filename),
        'filename': filename,
        'name': 'Realistic Backtest (Slippage + Spreads)',
        'strategy': 'RSI+BB Mean Reversion — Realistic',
        'generated_at': data.get('generated_at', ''),
        'type': 'realistic',
        'status': classify_status(metrics),
        'summary': {
            'total_trades': metrics.get('trades', 0),
            'wins': metrics.get('wins', 0),
            'losses': metrics.get('losses', 0),
            'win_rate_pct': metrics.get('win_rate', 0),
            'profit_factor': metrics.get('profit_factor', 0),
            'total_pnl_eur': metrics.get('total_pnl', 0),
            'max_dd_pct': data.get('max_drawdown_pct', 0),
            'expectancy': metrics.get('expectancy', 0),
            'avg_hold_hours': metrics.get('avg_hold_hours', 0),
        },
        'config': config,
        'per_pair': data.get('per_pair', {}),
        'exit_reasons': metrics.get('exit_reasons', {}),
        'session_breakdown': metrics.get('session_breakdown', {}),
        'costs': metrics.get('costs', {}),
        'bootstrap': data.get('bootstrap', {}),
        'verdict': data.get('verdict', ''),
        'issues': data.get('issues', []),
        'walk_forward': oos,
        'pairs': config.get('active_pairs', []),
    }
    return result


def extract_variant_backtests(data, filename):
    """Extract from variant_backtest_results.json — multiple variants."""
    results = []
    variants = data.get('results', [])
    for i, v in enumerate(variants):
        metrics = v.get('metrics', {})
        is_metrics = v.get('is_metrics', {})
        oos_metrics = v.get('oos_metrics', {})

        entry = {
            'id': make_id(filename) + f'_v{i}',
            'filename': filename,
            'name': v.get('variant', f'Variant {i}'),
            'strategy': 'RSI+BB Variant Comparison',
            'generated_at': data.get('generated_at', ''),
            'type': 'variant',
            'status': classify_status(metrics),
            'summary': {
                'total_trades': metrics.get('trades', 0),
                'wins': metrics.get('wins', 0),
                'losses': metrics.get('losses', 0),
                'win_rate_pct': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'total_pnl_eur': metrics.get('total_pnl', 0),
                'max_dd_pct': metrics.get('max_dd_pct', 0),
                'avg_pnl': metrics.get('avg_pnl', 0),
            },
            'exit_reasons': metrics.get('exit_reasons', {}),
            'is_metrics': is_metrics,
            'oos_metrics': oos_metrics,
            'variant_index': i,
            'variants_total': len(variants),
        }
        results.append(entry)
    return results


def extract_bot2_backtest(data, filename):
    """Extract from bot2_full_backtest.json."""
    before = data.get('portfolio_before_pruning', {})
    after = data.get('portfolio_after_pruning', {})
    result = {
        'id': make_id(filename),
        'filename': filename,
        'name': 'Bot #2 Full Portfolio Backtest',
        'strategy': 'EMA+ADX Trend Following',
        'generated_at': data.get('generated_at', ''),
        'type': 'bot2_portfolio',
        'status': classify_status(after if after else before),
        'summary': {
            'total_trades': after.get('trades', before.get('trades', 0)),
            'wins': after.get('wins', before.get('wins', 0)),
            'losses': after.get('losses', before.get('losses', 0)),
            'win_rate_pct': after.get('wr', before.get('wr', 0)),
            'profit_factor': after.get('pf', before.get('pf', 0)),
            'total_pnl_eur': after.get('total_pnl_eur', before.get('total_pnl_eur', 0)),
            'pairs_used': after.get('pairs_used', before.get('pairs_used', 0)),
        },
        'oos_validation': data.get('oos_validation', []),
        'optimal_pairs': data.get('optimal_pairs', []),
        'correlation': data.get('correlation', {}),
        'verdict': data.get('verdict', {}),
    }
    return result


def extract_deep_backtest(data, filename):
    """Extract from deep_backtest_results.json — filter variants."""
    variants = []
    for key, val in data.items():
        if not isinstance(val, dict):
            continue  # skip trade list arrays
        variants.append({
            'name': val.get('label', key),
            'key': key,
            'trades': val.get('trades', 0),
            'wins': val.get('wins', 0),
            'losses': val.get('losses', 0),
            'win_rate': val.get('win_rate', 0),
            'total_pnl': val.get('total_pnl', 0),
            'early_exits': val.get('early_exits', 0),
            'timeouts': val.get('timeouts', 0),
        })

    # Use baseline as main metrics
    baseline = data.get('baseline', {})
    result = {
        'id': make_id(filename),
        'filename': filename,
        'name': 'Deep Backtest — Filter Analysis',
        'strategy': 'RSI+BB Filter Variants',
        'generated_at': '',
        'type': 'deep_filter',
        'status': classify_status(baseline),
        'summary': {
            'total_trades': baseline.get('trades', 0),
            'wins': baseline.get('wins', 0),
            'losses': baseline.get('losses', 0),
            'win_rate_pct': baseline.get('win_rate', 0),
            'total_pnl_eur': baseline.get('total_pnl', 0),
        },
        'filter_variants': variants,
    }
    return result


def extract_backtest_v2(data, filename, filepath=None):
    """Extract from backtest v2 report.json files."""
    meta = data.get('meta', {})
    metrics = data.get('metrics', {})
    summary = metrics.get('summary', {})
    risk = metrics.get('risk', {})
    ratios = metrics.get('ratios', {})
    costs = metrics.get('costs', {})
    config = data.get('config', {})
    per_pair = data.get('per_pair', {})
    walk_forward = data.get('walk_forward', {})
    verdict = data.get('verdict', {})

    # Use parent dir name to distinguish v2 reports (bot1/report.json vs bot2/report.json)
    if filepath:
        parent_dir = os.path.basename(os.path.dirname(filepath))
        unique_name = f'{parent_dir}/{filename}'
    else:
        unique_name = filename

    result = {
        'id': make_id(unique_name),
        'filename': filename,
        'name': meta.get('bot', 'Backtest v2'),
        'strategy': 'Backtest Engine v2',
        'generated_at': meta.get('generated_at', ''),
        'type': 'backtest_v2',
        'status': verdict.get('status', 'CONDITIONAL'),
        'summary': {
            'total_trades': summary.get('trades', 0),
            'wins': summary.get('wins', 0),
            'losses': summary.get('losses', 0),
            'win_rate_pct': summary.get('win_rate', 0),
            'profit_factor': ratios.get('profit_factor', 0),
            'total_pnl_eur': summary.get('total_pnl', 0),
            'max_dd_pct': risk.get('max_drawdown_pct', 0),
            'sharpe': ratios.get('sharpe_ratio', 0),
            'sortino': ratios.get('sortino_ratio', 0),
            'calmar': risk.get('calmar_ratio', 0),
            'recovery_factor': risk.get('recovery_factor', 0),
            'final_equity': summary.get('final_equity', 0),
            'total_return_pct': summary.get('total_return_pct', 0),
            'expectancy': ratios.get('expectancy', 0),
        },
        'config': config,
        'per_pair': per_pair,
        'walk_forward': walk_forward,
        'verdict': verdict,
        'costs': costs,
        'exit_reasons': metrics.get('exit_reasons', {}),
        'session_breakdown': metrics.get('session_breakdown', {}),
        'monthly': metrics.get('monthly', {}),
        'trade_stats': metrics.get('trade_stats', {}),
    }
    return result


def extract_v3_report(data, filename, filepath=None):
    """Extract from v3 engine report.json files.

    v3 reports follow BACKTEST_V3_ARCHITECTURE.md Section 2.2 schema:
    - meta: run_id, engine_version, bot_label, data_range
    - summary: trades, wins, losses, win_rate, total_pnl, final_equity
    - risk: max_drawdown_pct, recovery_factor, calmar_ratio
    - ratios: profit_factor, sharpe_ratio, sortino_ratio, sqn, kelly_fraction, expectancy
    - statistical_validation: bootstrap_ci, monte_carlo, permutation_test
    - walk_forward: n_splits, passed, splits[]
    - equity_curve: points[] with unrealized PnL
    - trades: full trade list
    - per_pair, costs, monthly, degradation, rolling_metrics
    - verdict: rating + criteria
    """
    meta = data.get('meta', {})
    summary = data.get('summary', {})
    risk = data.get('risk', {})
    ratios = data.get('ratios', {})
    sv = data.get('statistical_validation', {})
    boot = sv.get('bootstrap_ci', {})
    wf = data.get('walk_forward', {})
    verdict = data.get('verdict', {})
    costs = data.get('costs', {})

    run_id = meta.get('run_id', '')

    result = {
        'id': run_id if run_id else make_id(filename),
        'filename': filename,
        'name': meta.get('bot_label', 'Backtest v3'),
        'strategy': f"Backtest Engine v3 ({meta.get('bot_label', 'Unknown')})",
        'generated_at': meta.get('created_at', ''),
        'type': 'backtest_v3',
        'engine_version': meta.get('engine_version', '3.0.0'),
        'status': verdict.get('rating', classify_status(summary)),

        # Pass through meta for v3 detection
        'meta': meta,

        'summary': {
            'total_trades': summary.get('trades', 0),
            'wins': summary.get('wins', 0),
            'losses': summary.get('losses', 0),
            'win_rate': summary.get('win_rate', 0),
            'win_rate_pct': summary.get('win_rate', 0),
            'total_pnl': summary.get('total_pnl', 0),
            'total_pnl_eur': summary.get('total_pnl', 0),
            'final_equity': summary.get('final_equity', 0),
            'total_return_pct': summary.get('total_return_pct', 0),
            'sharpe': ratios.get('sharpe_ratio', 0),
            'max_dd_pct': risk.get('max_drawdown_pct', 0),
            'profit_factor': ratios.get('profit_factor', 0),
            'sortino': ratios.get('sortino_ratio', 0),
            'calmar': risk.get('calmar_ratio', 0),
            'recovery_factor': risk.get('recovery_factor', 0),
            'expectancy': ratios.get('expectancy', 0),
        },

        'risk': risk,
        'ratios': ratios,
        'statistical_validation': sv,
        'walk_forward': wf,
        'equity_curve': data.get('equity_curve', {}),
        'trades': data.get('trades', [])[:1000],  # limit for API size
        'total_trade_count': len(data.get('trades', [])),
        'per_pair': data.get('per_pair', {}),
        'costs': costs,
        'monthly': data.get('monthly', {}),
        'degradation': data.get('degradation', {}),
        'rolling_metrics': data.get('rolling_metrics', {}),
        'exit_reasons': data.get('exit_reasons', {}),
        'session_breakdown': data.get('session_breakdown', {}),
        'score_distribution': data.get('score_distribution', {}),
        'verdict': verdict,
        'config': data.get('config', {}),
    }
    return result


def extract_simple(data, filename, name, strategy, bt_type):
    """Generic extractor for simpler backtest files."""
    metrics = {}
    # Try to find metrics in common locations
    for key in ['metrics', 'summary', 'results']:
        if key in data and isinstance(data[key], dict):
            metrics = data[key]
            break

    result = {
        'id': make_id(filename),
        'filename': filename,
        'name': name,
        'strategy': strategy,
        'generated_at': data.get('generated_at', ''),
        'type': bt_type,
        'status': classify_status(metrics),
        'summary': {
            'total_trades': metrics.get('trades', metrics.get('total_trades', 0)),
            'wins': metrics.get('wins', 0),
            'losses': metrics.get('losses', 0),
            'win_rate_pct': metrics.get('win_rate', metrics.get('win_rate_pct', 0)),
            'profit_factor': metrics.get('profit_factor', metrics.get('pf', 0)),
            'total_pnl_eur': metrics.get('total_pnl', metrics.get('total_pnl_eur', 0)),
            'max_dd_pct': metrics.get('max_dd_pct', metrics.get('max_drawdown_pct', 0)),
        },
        'raw_keys': list(data.keys())[:20],
    }
    return result


# ── SQLite DB Reader ───────────────────────────────────────

def extract_v3_from_db(db_path=BACKTEST_V3_DIR + '/history.db'):
    """Read all v3 runs from SQLite DB that don't already have JSON files."""
    import sqlite3 as sqlite3_mod

    if not os.path.exists(db_path):
        return []

    conn = sqlite3_mod.connect(db_path)
    conn.row_factory = sqlite3_mod.Row

    try:
        rows = conn.execute(
            "SELECT run_id, created_at, config_json, bot_id, pairs, "
            "total_trades, win_rate, profit_factor, sharpe_ratio, "
            "total_pnl, max_dd_pct, sqn, wf_passed, wf_splits, "
            "wf_profitable, notes "
            "FROM runs ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        run_id = row['run_id']
        config = {}
        try:
            config = json.loads(row['config_json']) if row['config_json'] else {}
        except (json.JSONDecodeError, TypeError):
            pass

        bot_id = row['bot_id']
        bot_labels = {1: 'Bot #1 (Mean Reversion)', 2: 'Bot #2 (Trend Following)', 3: 'Bot #3'}
        bot_label = bot_labels.get(bot_id, f'Bot #{bot_id}')

        # Build summary from DB columns
        summary = {
            'total_trades': row['total_trades'] or 0,
            'win_rate': row['win_rate'] or 0,
            'win_rate_pct': row['win_rate'] or 0,
            'profit_factor': row['profit_factor'] or 0,
            'total_pnl': row['total_pnl'] or 0,
            'total_pnl_eur': row['total_pnl'] or 0,
            'sharpe': row['sharpe_ratio'] or 0,
            'max_dd_pct': row['max_dd_pct'] or 0,
        }

        # Classify status
        status = classify_status(summary)

        result = {
            'id': run_id,
            'filename': f'{run_id}.json',
            'name': bot_label,
            'strategy': f'Backtest Engine v3 ({bot_label})',
            'generated_at': row['created_at'] or '',
            'type': 'backtest_v3',
            'engine_version': '3.0.0',
            'status': status,

            'meta': {
                'run_id': run_id,
                'created_at': row['created_at'] or '',
                'engine_version': '3.0.0',
                'bot_id': bot_id,
                'bot_label': bot_label,
            },

            'summary': summary,
            'ratios': {
                'profit_factor': row['profit_factor'] or 0,
                'sharpe_ratio': row['sharpe_ratio'] or 0,
                'sqn': row['sqn'] or 0,
            },
            'risk': {
                'max_drawdown_pct': row['max_dd_pct'] or 0,
            },
            'walk_forward': {
                'passed': bool(row['wf_passed']),
                'n_splits': row['wf_splits'] or 0,
                'profitable_splits': row['wf_profitable'] or 0,
            },
            'config': config,
            'notes': row['notes'] or '',

            # Flag: this is a DB-only entry (no full JSON detail)
            '_from_db': True,
        }
        results.append(result)

    return results


def scan_api_dir_for_v3():
    """Scan the API directory for engine-exported v3 JSON files."""
    results = []
    if not os.path.isdir(API_DIR):
        return results

    for fname in sorted(os.listdir(API_DIR)):
        if not fname.endswith('.json'):
            continue
        if fname.startswith('bt_') or fname == 'index.json':
            continue  # Skip build-script generated files and index

        fpath = os.path.join(API_DIR, fname)
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if not isinstance(data, dict):
            continue

        engine_version = data.get('meta', {}).get('engine_version', '')
        if not engine_version.startswith('3'):
            continue

        # Use filename (without .json) as run_id — matches DB
        run_id = fname.replace('.json', '')
        if not data.get('meta', {}).get('run_id'):
            data.setdefault('meta', {})['run_id'] = run_id

        entry = extract_v3_report(data, fname, fpath)
        # Ensure id is the run_id from filename
        entry['id'] = run_id
        results.append(entry)

    return results


# ── Main ────────────────────────────────────────────────────

def main():
    os.makedirs(API_DIR, exist_ok=True)

    # Scan all JSON files
    all_reports = []
    seen_ids = set()
    extractors = {
        'combined_backtest_report.json': lambda d, f: [extract_combined_report(d, f)],
        'realistic_backtest_report.json': lambda d, f: [extract_realistic_backtest(d, f)],
        'variant_backtest_results.json': lambda d, f: extract_variant_backtests(d, f),
        'bot2_full_backtest.json': lambda d, f: [extract_bot2_backtest(d, f)],
        'deep_backtest_results.json': lambda d, f: [extract_deep_backtest(d, f)],
    }

    simple_mappings = {
        'cot_intermarket_backtest.json': ('COT Intermarket Backtest', 'COT + Intermarket Analysis', 'cot'),
    }

    # Skip optimization/analysis files that aren't backtest reports
    skip_files = {
        'balanced_optimization.json', 'comprehensive_optimization.json',
        'full_rr_optimization.json', 'trade_frequency_optimization.json',
        'full_backtest_analysis.json', 'optimization_analysis.json',
    }

    # Scan main data dir + backtest_v2 dir (including subdirs) + backtest_v3 dir
    json_files = sorted(glob.glob(os.path.join(DATA_DIR, '*.json')))
    if os.path.isdir(BACKTEST_V2_DIR):
        json_files += sorted(glob.glob(os.path.join(BACKTEST_V2_DIR, '*.json')))
        # Also scan subdirectories (bot1/, bot2/, both/)
        for subdir in glob.glob(os.path.join(BACKTEST_V2_DIR, '*/')):
            json_files += sorted(glob.glob(os.path.join(subdir, '*.json')))
    if os.path.isdir(BACKTEST_V3_DIR):
        json_files += sorted(glob.glob(os.path.join(BACKTEST_V3_DIR, '*.json')))
        # Also scan subdirectories (one per run_id)
        for subdir in glob.glob(os.path.join(BACKTEST_V3_DIR, '*/')):
            json_files += sorted(glob.glob(os.path.join(subdir, '*.json')))
    processed = 0

    # ── Phase 1: Scan engine-exported v3 files in API dir FIRST ──
    api_v3_entries = scan_api_dir_for_v3()
    for entry in api_v3_entries:
        all_reports.append(entry)
        seen_ids.add(entry['id'])
        # Track created_at for dedup against report.json
        seen_created_at = entry.get('generated_at', '')
        processed += 1
        print(f'  [API-SCAN   ] {entry["id"]} — {entry["name"]}')

    # ── Phase 2: Scan data dirs (original logic, with dedup) ──
    for fpath in json_files:
        fname = os.path.basename(fpath)
        if fname in skip_files:
            continue
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if not isinstance(data, dict):
            continue

        if fname in extractors:
            entries = extractors[fname](data, fname)
            for entry in entries:
                if entry['id'] not in seen_ids:
                    all_reports.append(entry)
                    seen_ids.add(entry['id'])
                    # Write detail file
                    detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
                    with open(detail_path, 'w') as f:
                        json.dump(entry, f, indent=2, default=str)
                    processed += 1
        elif fname in simple_mappings:
            name, strategy, bt_type = simple_mappings[fname]
            entry = extract_simple(data, fname, name, strategy, bt_type)
            if entry['id'] not in seen_ids:
                all_reports.append(entry)
                seen_ids.add(entry['id'])
                detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
                with open(detail_path, 'w') as f:
                    json.dump(entry, f, indent=2, default=str)
                processed += 1
        elif fname == 'report.json':
            # Distinguish v2 vs v3 by engine_version
            engine_version = data.get('meta', {}).get('engine_version', '')
            if engine_version.startswith('3'):
                # v3 report — skip if API-SCAN already found this run
                created_at = data.get('meta', {}).get('created_at', '')
                if any(e.get('generated_at') == created_at for e in all_reports):
                    continue  # Already covered by API-SCAN
                entry = extract_v3_report(data, fname, fpath)
                if entry['id'] not in seen_ids:
                    all_reports.append(entry)
                    seen_ids.add(entry['id'])
                    detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
                    with open(detail_path, 'w') as f:
                        json.dump(entry, f, indent=2, default=str)
                    processed += 1
            elif data.get('meta', {}).get('engine_version') == 'v2':
                # v2 report
                entry = extract_backtest_v2(data, fname, fpath)
                if entry['id'] not in seen_ids:
                    all_reports.append(entry)
                    seen_ids.add(entry['id'])
                    detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
                    with open(detail_path, 'w') as f:
                        json.dump(entry, f, indent=2, default=str)
                    processed += 1
        elif fname.endswith('.json') and isinstance(data, dict) and data.get('meta', {}).get('engine_version', '').startswith('3'):
            # Generic v3 report with different filename
            entry = extract_v3_report(data, fname, fpath)
            if entry['id'] not in seen_ids:
                all_reports.append(entry)
                seen_ids.add(entry['id'])
                detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
                with open(detail_path, 'w') as f:
                    json.dump(entry, f, indent=2, default=str)
                processed += 1

    # ── Phase 3: Scan SQLite DB for remaining v3 runs ──
    db_entries = extract_v3_from_db()
    for entry in db_entries:
        if entry['id'] not in seen_ids:
            all_reports.append(entry)
            seen_ids.add(entry['id'])
            # Write detail file for DB-only entries
            detail_path = os.path.join(API_DIR, f'{entry["id"]}.json')
            # Remove internal flag before writing
            detail = {k: v for k, v in entry.items() if not k.startswith('_')}
            with open(detail_path, 'w') as f:
                json.dump(detail, f, indent=2, default=str)
            processed += 1
            print(f'  [DB-SCAN    ] {entry["id"]} — {entry["name"]}')

    # Sort by generated_at descending
    all_reports.sort(key=lambda x: x.get('generated_at', '') or '', reverse=True)

    # Write index
    index = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_backtests': len(all_reports),
        'backtests': all_reports,
    }
    with open(os.path.join(API_DIR, 'index.json'), 'w') as f:
        json.dump(index, f, indent=2, default=str)

    print(f'Generated backtest API: {processed} reports indexed')
    print(f'  Index: {API_DIR}/index.json')
    for r in all_reports:
        print(f'  [{r["status"]:12s}] {r["id"]} — {r["name"]}')


if __name__ == '__main__':
    main()
