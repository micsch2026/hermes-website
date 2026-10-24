#!/usr/bin/env python3
"""Tests fuer build_seed_pipeline_status.py (API-Projektion /strategy-lab + /supervisor)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
import build_seed_pipeline_status as b  # noqa: E402

fails = []


def check(name, ok, detail=None):
    if detail is None:
        detail = ""
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="seed-pipeline-test-") as td:
        td = Path(td)
        src, out = td / "seed_registry.json", td / "seed_pipeline.json"
        src.write_text(json.dumps({
            "generated_bz": "24.10.2026 15:49 BZ",
            "summary": {"seeds_total": 1539, "seeds_with_strategy": 315,
                        "seeds_with_B": 136, "zero_yield": 1224,
                        "zero_yield_gt60": 257, "alt_data_seeds": 8,
                        "clusters": 83, "approach_slots": 662,
                        "families_with_zero": 0},
            "families": [{"family": "F2", "seeds": 379, "strategies": 296, "B": 78}],
            "caps": {"seeds_gt5_strategies": [{"seed": "split_214", "strategies": 92}],
                     "clusters_gt20_approaches": [{"cluster": "expand", "approaches": 172}]},
            "sources": [{"source": "auto", "seeds": 645}],
            "orphan_winners": [{"seed": "x"}],
        }), encoding="utf-8")
        rc = b.build(src=src, out=out)
        d = json.loads(out.read_text(encoding="utf-8"))
        check("build: rc 0", rc == 0, rc)
        check("build: available", d.get("available") is True, d)
        check("build: summary seeds_total", d["summary"]["seeds_total"] == 1539, d["summary"])
        check("build: generated_bz", d.get("generated_bz") == "24.10.2026 15:49 BZ", d.get("generated_bz"))
        check("build: family pass-through", d["families"][0]["family"] == "F2", d["families"])
        check("build: caps pass-through", d["caps"]["clusters_gt20_approaches"][0]["approaches"] == 172, d["caps"])
        check("build: no tmp", list(td.glob("*.tmp")) == [])

        rc = b.build(src=td / "missing.json", out=td / "missing_out.json")
        d = json.loads((td / "missing_out.json").read_text(encoding="utf-8"))
        check("missing: rc 1", rc == 1, rc)
        check("missing: available false", d.get("available") is False, d)

    print()
    if fails:
        print(f"{len(fails)} FAIL: {fails}")
        return 1
    print("ALLE CHECKS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
