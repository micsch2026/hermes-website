#!/usr/bin/env python3
"""test_execution_guard.py — hermetische Tests fuer
build_overview_status.execution_guard_section (Kachel „Execution-Schutz", 2026-10-10).

Kein Netz/keine Live-Daten: tmp-Report-Datei + Fake-TCA-Dict. Deckt: Feld-Mapping,
Verdikt-Regel (defended/costs/thin, n>=5-Schwelle wie die Loop-Logik), report_age_h,
neuester Report gewinnt, fehlender Report -> None (fail-soft), kaputte JSON -> None,
TCA-None -> None. Run: python3 tests/test_execution_guard.py → exit 1 bei FAIL.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import build_overview_status as m  # noqa: E402

NOW_DT = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

FAILURES = []
N_CHECK = 0


def check(name, cond, detail=""):
    global N_CHECK
    N_CHECK += 1
    print(f"  {'✅' if cond else '❌'} {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(name)


def _write_report(root, name, doc, age_s=None):
    d = os.path.join(root, "data", "reports")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False))
    if age_s is not None:
        mt = NOW_DT.timestamp() - age_s
        os.utime(p, (mt, mt))
    return p


def _rep(**tot_over):
    tot = {"n_signals": 5, "n_matched": 5, "n_unmatched": 0, "saved_eur_sum": -17.99,
           "missed_profit_n": 3, "avoided_loss_n": 2, "win_n": 3, "loss_n": 2,
           "drift_p_median": 54.0, "near_fill_n": 2}
    tot.update(tot_over)
    return {"schema": "guard_counterfactual_v1",
            "generated_at_utc": "2026-10-10T07:36:37+00:00", "days": 7,
            "window": {"start": "2026-10-03T07:36:37+00:00",
                       "end": "2026-10-10T07:36:37+00:00"},
            "totals": tot}


TCA_FAKE = {"n_eligible": 12, "coverage_pct": 5.13, "since": None,
            "groups": {"overall": {"median_bps": -1.6, "p90_bps": 1.08,
                                   "mean_bps": -0.88, "adverse_pct": 16.67}}}


def main():
    tmp = tempfile.mkdtemp(prefix="execguard_test_")
    tmp2 = tempfile.mkdtemp(prefix="execguard_empty_")
    tmp3 = tempfile.mkdtemp(prefix="execguard_bad_")
    try:
        # 1) Mapping + verdict=costs (n>=5, saved<0) + Alter
        _write_report(tmp, "guard_counterfactual_20261010.json",
                      _rep(), age_s=2 * 3600)
        out = m.execution_guard_section(tmp, TCA_FAKE, NOW_DT)
        cf = out.get("counterfactual") or {}
        check("counterfactual gefunden", cf.get("file") == "guard_counterfactual_20261010.json")
        check("Feld-Mapping", cf.get("days") == 7 and cf.get("n_signals") == 5
              and cf.get("saved_eur_sum") == -17.99 and cf.get("avoided_loss_n") == 2
              and cf.get("missed_profit_n") == 3 and cf.get("near_fill_n") == 2
              and cf.get("window_start") == "2026-10-03T07:36:37+00:00")
        check("Verdikt costs (n>=5, saved<0)", cf.get("verdict") == "costs")
        check("report_age_h ≈ 2.0",
              isinstance(cf.get("report_age_h"), float) and abs(cf["report_age_h"] - 2.0) < 0.2,
              str(cf.get("report_age_h")))
        check("TCA-Mapping", out["tca"]["median_bps"] == -1.6
              and out["tca"]["coverage_pct"] == 5.13 and out["tca"]["n_eligible"] == 12
              and out["tca"]["p90_bps"] == 1.08)

        # 2) Neuester Report gewinnt + verdikt defended
        _write_report(tmp, "guard_counterfactual_20261011.json",
                      _rep(n_signals=34, saved_eur_sum=58.63), age_s=3600)
        out2 = m.execution_guard_section(tmp, TCA_FAKE, NOW_DT)
        check("neuester Report gewinnt",
              out2["counterfactual"]["file"] == "guard_counterfactual_20261011.json")
        check("Verdikt defended (saved>0)", out2["counterfactual"]["verdict"] == "defended")

        # 3) thin wegen n<5
        _write_report(tmp, "guard_counterfactual_20261012.json",
                      _rep(n_signals=3), age_s=60)
        out3 = m.execution_guard_section(tmp, TCA_FAKE, NOW_DT)
        check("Verdikt thin (n<5)", out3["counterfactual"]["verdict"] == "thin")

        # 4) thin wegen saved=None
        _write_report(tmp, "guard_counterfactual_20261013.json",
                      _rep(saved_eur_sum=None), age_s=60)
        out3b = m.execution_guard_section(tmp, TCA_FAKE, NOW_DT)
        check("Verdikt thin (saved None)", out3b["counterfactual"]["verdict"] == "thin")

        # 5) Kein Report -> counterfactual None, TCA bleibt
        out4 = m.execution_guard_section(tmp2, TCA_FAKE, NOW_DT)
        check("kein Report -> counterfactual None", out4["counterfactual"] is None)
        check("kein Report -> TCA trotzdem da", out4["tca"] is not None)

        # 6) Kaputte JSON -> None (fail-soft)
        _write_report(tmp3, "guard_counterfactual_bad.json", "{kaputt", age_s=60)
        out5 = m.execution_guard_section(tmp3, TCA_FAKE, NOW_DT)
        check("kaputte JSON -> counterfactual None", out5["counterfactual"] is None)

        # 7) tca=None -> tca None
        out6 = m.execution_guard_section(tmp, None, NOW_DT)
        check("tca=None -> tca None", out6["tca"] is None)
    finally:
        for d in (tmp, tmp2, tmp3):
            shutil.rmtree(d, ignore_errors=True)

    print()
    if FAILURES:
        print(f"FEHLGESCHLAGEN: {len(FAILURES)} Checks: {FAILURES}")
        return 1
    print(f"RESULT: ALL PASS ({N_CHECK} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
