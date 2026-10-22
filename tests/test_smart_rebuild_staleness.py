#!/usr/bin/env python3
"""test_smart_rebuild_staleness.py — Staleness-Guard des Site-Rebuilders.

FIX 2026-10-22: run_build() baute bisher NUR bei Quell-mtime-Aenderung;
max_staleness_hours wurde im Entscheid ignoriert -> statisches src/ => ewige
Skip-Schleife und 'Build stale'-Watchdog-Alarme (33h > 26h). Die Fixtures
pinnen alle Zweige: changed / fresh-skip / stale-rebuild / Grenze / Guard aus /
State-Refresh (fehlender & kaputter last_build).

Run:  python3 tests/test_smart_rebuild_staleness.py   -> alle PASS / exit 1 bei FAIL
"""

import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import smart_rebuild as m  # noqa: E402

NOW = datetime(2026, 10, 22, 6, 0, 0, tzinfo=timezone.utc)  # fixer Zeitanker
NOW_EPOCH = NOW.timestamp()

CFG = {"max_staleness_hours": 24.0}


def state_with(last_build_age_h, mtime=100):
    st: dict = {"mtime": mtime}
    if last_build_age_h is not None:
        st["last_build"] = datetime.fromtimestamp(
            NOW_EPOCH - last_build_age_h * 3600, tz=timezone.utc).isoformat()
    return {"site": st}


def main():
    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"FAIL  {name}  [{e}]")

    def t1():
        should, reason = m.rebuild_decision("site", CFG, state_with(1.0, mtime=100),
                                            now_epoch=NOW_EPOCH, current_mtime=200)
        assert should and "changes detected" in reason, (should, reason)
    check("changed mtime -> rebuild", t1)

    def t2():
        should, reason = m.rebuild_decision("site", CFG, state_with(2.0),
                                            now_epoch=NOW_EPOCH, current_mtime=100)
        assert not should and "no changes" in reason, (should, reason)
    check("fresh, no change -> skip", t2)

    def t3():
        should, reason = m.rebuild_decision("site", CFG, state_with(25.0),
                                            now_epoch=NOW_EPOCH, current_mtime=100)
        assert should and "stale" in reason and "25.0h" in reason, (should, reason)
    check("stale (25h >= 24h) -> rebuild", t3)

    def t4():
        should, _ = m.rebuild_decision("site", CFG, state_with(24.0),
                                       now_epoch=NOW_EPOCH, current_mtime=100)
        assert should
    check("boundary 24h -> rebuild (>=)", t4)

    def t5():
        should, _ = m.rebuild_decision("site", {}, state_with(500.0),
                                       now_epoch=NOW_EPOCH, current_mtime=100)
        assert not should
    check("guard off (no limit) -> skip", t5)

    def t6():
        should, reason = m.rebuild_decision("site", CFG, {"site": {"mtime": 100}},
                                            now_epoch=NOW_EPOCH, current_mtime=100)
        assert should and "refresh" in reason, (should, reason)
    check("missing last_build -> rebuild once", t6)

    def t7():
        st = {"site": {"mtime": 100, "last_build": "not-a-date"}}
        should, reason = m.rebuild_decision("site", CFG, st,
                                            now_epoch=NOW_EPOCH, current_mtime=100)
        assert should and "refresh" in reason, (should, reason)
    check("unparsable last_build -> rebuild once", t7)

    print(f"\n{7 - len(failures)}/7 PASS, {len(failures)} FAIL")
    if failures:
        print("FAILS:", failures)
        sys.exit(1)
    print("ALLE PASS")


if __name__ == "__main__":
    main()
