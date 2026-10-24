#!/usr/bin/env python3
"""build_seed_pipeline_status.py — API-Projektion der Lab-Seed-Pipeline.

Liest den read-only Registry-Report aus /root/strategy-lab/data/reports/seed_registry.json
und schreibt eine kompakte, oeffentliche JSON-Projektion fuer /strategy-lab und
/supervisor. Keine DB-Schreibzugriffe, keine Secrets, kein LLM.

ENV: SEED_REGISTRY_JSON, SEED_PIPELINE_OUT.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent
DEFAULT_SRC = Path("/root/strategy-lab/data/reports/seed_registry.json")
DEFAULT_OUT = SITE / "api/strategy-lab/seed_pipeline.json"
SUMMARY_KEYS = (
    "seeds_total", "seeds_with_strategy", "seeds_with_B", "pct_with_strategy",
    "pct_with_B", "zero_yield", "zero_yield_gt60", "referenced_zero",
    "referenced_zero_gt60", "alt_data_seeds", "event_seeds", "rules_gt3",
    "rules_gt3_pct", "orphan_winners", "clusters", "approach_slots",
    "unmapped_seeds", "families_with_zero",
)


def _atomic_write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def build(src: Path | str | None = None, out: Path | str | None = None) -> int:
    src = Path(src or os.environ.get("SEED_REGISTRY_JSON") or DEFAULT_SRC)
    out = Path(out or os.environ.get("SEED_PIPELINE_OUT") or DEFAULT_OUT)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not src.exists():
        _atomic_write(out, {
            "schema": "seed_pipeline_v1", "generated_at": now, "available": False,
            "error": f"Registry fehlt: {src}", "summary": {}, "families": [],
            "caps": {}, "sources": [], "orphan_winners": [],
        })
        print(f"MISSING {src}", file=sys.stderr)
        return 1

    try:
        d = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _atomic_write(out, {
            "schema": "seed_pipeline_v1", "generated_at": now, "available": False,
            "error": f"Registry unlesbar: {e}", "summary": {}, "families": [],
            "caps": {}, "sources": [], "orphan_winners": [],
        })
        print(f"ERROR {e}", file=sys.stderr)
        return 1

    summary = {k: (d.get("summary") or {}).get(k) for k in SUMMARY_KEYS}
    doc = {
        "schema": "seed_pipeline_v1",
        "generated_at": now,
        "available": True,
        "generated_bz": d.get("generated_bz"),
        "summary": summary,
        "families": d.get("families") or [],
        "caps": {
            "seeds_gt5_strategies": (d.get("caps") or {}).get("seeds_gt5_strategies") or [],
            "clusters_gt20_approaches": (d.get("caps") or {}).get("clusters_gt20_approaches") or [],
        },
        "sources": d.get("sources") or [],
        "orphan_winners": (d.get("orphan_winners") or [])[:12],
    }
    _atomic_write(out, doc)
    print(f"OK {out} ({out.stat().st_size} bytes) seeds={summary.get('seeds_total')} "
          f"families={len(doc['families'])}")
    return 0


def main() -> int:
    return build()


if __name__ == "__main__":
    sys.exit(main())
