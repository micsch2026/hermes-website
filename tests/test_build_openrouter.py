#!/usr/bin/env python3
"""Tests fuer build_openrouter_status.py (Datenlayer /supervisor, Schema openrouter_v1).

Laeuft OHNE Netz (fetch wird injiziert), isoliert in einem temp-Verzeichnis
(env-Datei + History + OUT) — schreibt NIE in api/.
Ausfuehrung: cd site && /usr/bin/python3 tests/test_build_openrouter.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))
import build_openrouter_status as b  # noqa: E402

fails = []


def check(name, ok, detail=None):
    if detail is None:
        detail = ""
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


def _snap(credits=50.0, used=32.0, daily=1.0, weekly=7.0, monthly=20.0):
    return {"credits": {"total_credits": credits, "total_usage": used},
            "key": {"usage_daily": daily, "usage_weekly": weekly,
                    "usage_monthly": monthly}}


def _lines(path: Path):
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openrouter-test-") as td:
        td = Path(td)

        # ---- 1) _read_key ------------------------------------------------
        env = td / ".env"
        env.write_text("# OPENROUTER_API_KEY=sk-fake\n"
                       "OPENROUTER_API_KEY=sk-real-123\n", encoding="utf-8")
        check("_read_key: Kommentarzeile uebersprungen -> echter Wert",
              b._read_key(env) == "sk-real-123", b._read_key(env))
        env_none = td / ".env.none"
        env_none.write_text("OTHER=1\n# OPENROUTER_API_KEY=sk-x\n", encoding="utf-8")
        check("_read_key: ohne Key -> None", b._read_key(env_none) is None,
              b._read_key(env_none))
        check("_read_key: fehlende Datei -> None",
              b._read_key(td / "gibt-es-nicht") is None)

        hist = td / "usage_history.jsonl"
        out = td / "status.json"
        t0 = 1_700_000_000.0

        def run(ts, snap, exc=None):
            def fetch(key, timeout):
                if exc is not None:
                    raise exc
                return snap
            return b.build(fetch=fetch, env_file=env, history_path=hist,
                           out_path=out, timeout=5, now_ts=ts, token_history=[])

        # ---- 2) Erster Lauf (leere History) ------------------------------
        rc = run(t0, _snap())
        check("Lauf 1: Rueckgabe 0", rc == 0, rc)
        check("Lauf 1: status.json existiert", out.exists())
        d = _read(out)
        check("Lauf 1: schema openrouter_v1", d.get("schema") == "openrouter_v1", d.get("schema"))
        check("Lauf 1: balance.remaining == 18.0",
              d["balance"]["remaining"] == 18.0, d["balance"])
        check("Lauf 1: used_pct == 64.0",
              d["balance"]["used_pct"] == 64.0, d["balance"]["used_pct"])
        check("Lauf 1: burn_7d_per_day == 1.0",
              d["spend"]["burn_7d_per_day"] == 1.0, d["spend"])
        check("Lauf 1: runway_days == 18.0",
              d["spend"]["runway_days"] == 18.0, d["spend"])
        check("Lauf 1: history_n == 1", d["history_n"] == 1, d["history_n"])
        check("Lauf 1: fetch_ok is True", d["fetch_ok"] is True)
        check("Lauf 1: History-Datei 1 Zeile", len(_lines(hist)) == 1, _lines(hist))
        check("Lauf 1: history-Feld 1 Punkt", len(d["history"]) == 1, d["history"])
        check("Lauf 1: usage_history leer (injiziert)", d.get("usage_history") == [], d.get("usage_history"))
        check("Lauf 1: cost_history 1 Tag", len(d.get("cost_history") or []) == 1, d.get("cost_history"))

        # ---- 3) Gleiche Werte, ts +300 s -> kein neuer Punkt -------------
        rc = run(t0 + 300, _snap())
        d = _read(out)
        check("Lauf 2 (ts+300): kein neuer Punkt (history_n == 1)",
              d["history_n"] == 1, d["history_n"])
        check("Lauf 2 (ts+300): History-Datei unveraendert 1 Zeile",
              len(_lines(hist)) == 1, len(_lines(hist)))

        # ---- 4) Geaenderter used (+0.5) -> neuer Punkt -------------------
        rc = run(t0 + 600, _snap(used=32.5))
        d = _read(out)
        check("Lauf 3 (used+0.5): history_n == 2", d["history_n"] == 2, d["history_n"])
        check("Lauf 3: History-Datei 2 Zeilen", len(_lines(hist)) == 2, len(_lines(hist)))

        # ---- 5) Gleiche Werte, ts +3601 s -> Heartbeat-Punkt -------------
        rc = run(t0 + 600 + 3601, _snap(used=32.5))
        d = _read(out)
        check("Lauf 4 (ts+3601): Heartbeat -> history_n == 3",
              d["history_n"] == 3, d["history_n"])
        check("Lauf 4: History-Datei 3 Zeilen", len(_lines(hist)) == 3, len(_lines(hist)))

        # ---- 6) Fetch-Exception beim naechsten Lauf -> fail-soft ---------
        before = _read(out)
        rc = run(t0 + 9000, None, exc=RuntimeError("HTTP 503 bei credits"))
        check("Lauf 5 (Exception): Rueckgabe 1", rc == 1, rc)
        d = _read(out)
        check("Lauf 5: fetch_ok is False", d["fetch_ok"] is False, d["fetch_ok"])
        check("Lauf 5: fetch_error gesetzt", bool(d.get("fetch_error")), d.get("fetch_error"))
        check("Lauf 5: balance-Werte erhalten", d["balance"] == before["balance"], d["balance"])
        check("Lauf 5: History unveraendert 3 Zeilen",
              len(_lines(hist)) == 3, len(_lines(hist)))

        # ---- 6b) Fail-soft ohne valides Vorher-Dokument ------------------
        out2 = td / "frisch" / "status.json"
        rc = b.build(fetch=lambda k, t: (_ for _ in ()).throw(RuntimeError("kaputt")),
                     env_file=env, history_path=td / "h2.jsonl",
                     out_path=out2, timeout=5, now_ts=t0, token_history=[])
        check("Lauf 6 (kein Vorher-Dok): Rueckgabe 1", rc == 1, rc)
        d2 = _read(out2)
        check("Lauf 6: Minimal-Dokument (balance null, history [])",
              d2["balance"] is None and d2["history"] == [] and d2["history_n"] == 0
              and d2["fetch_ok"] is False, d2)

        # ---- 6c) state.db Token-Tagesaggregat (read-only) ----------------
        db = td / "state.db"
        d0 = t0 - 12 * 3600  # noon-ish UTC, damit +1h nicht die Berliner Tagesgrenze kreuzt
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE sessions (started_at REAL, input_tokens INT, output_tokens INT, "
                    "cache_read_tokens INT, cache_write_tokens INT)")
        con.executemany("INSERT INTO sessions VALUES (?,?,?,?,?)", [
            (d0, 100, 20, 5, 1),
            (d0 + 3600, 50, 10, 0, 0),
            (d0 + 86400, 7, 3, 2, 0),
        ])
        con.commit()
        con.close()
        th = b.load_token_history(db, now_ts=t0 + 2 * 86400)
        check("load_token_history: 2 Tage", len(th) == 2, th)
        if len(th) == 2:
            check("load_token_history: Tag 1 tokens_io == 180", th[0]["tokens_io"] == 180, th[0])
            check("load_token_history: Tag 1 tokens == 186", th[0]["tokens"] == 186, th[0])
            check("load_token_history: Tag 1 sessions == 2", th[0]["sessions"] == 2, th[0])
            check("load_token_history: Tag 2 tokens == 12", th[1]["tokens"] == 12, th[1])
        check("load_token_history: fehlende DB -> []",
              b.load_token_history(td / "nope.db") == [])

        ch = b.build_cost_history([
            {"ts": t0, "used": 10.0, "remaining": 40.0},
            {"ts": t0 + 60, "used": 10.5, "remaining": 39.5},
            {"ts": t0 + 86400, "used": 12.0, "remaining": 38.0},
        ])
        check("build_cost_history: 2 Tage, letzter Tageswert gewinnt",
              len(ch) == 2 and ch[0]["used"] == 10.5 and ch[1]["used"] == 12.0, ch)

        # ---- 7) _downsample mit 5000 synthetischen Punkten ---------------
        entries = [[1000.0 + i, float(100 + (i % 37) - 18), float(i)] for i in range(5000)]
        ds = b._downsample(entries, 1500)
        check("_downsample: Laenge <= 1508", len(ds) <= 1508, len(ds))
        check("_downsample: erster Punkt erhalten", ds[0] == entries[0], ds[0])
        check("_downsample: letzter Punkt erhalten", ds[-1] == entries[-1], ds[-1])
        rems = [p[1] for p in ds]
        allr = [p[1] for p in entries]
        check("_downsample: globales Min enthalten", min(allr) in rems, min(allr))
        check("_downsample: globales Max enthalten", max(allr) in rems, max(allr))
        check("_downsample: ts aufsteigend",
              all(ds[i][0] < ds[i + 1][0] for i in range(len(ds) - 1)))

        # ---- 8) Kein .tmp-Rueckstand ------------------------------------
        tmps = list(td.rglob("*.tmp"))
        check("kein .tmp-Rueckstand", tmps == [], tmps)

    print()
    if fails:
        print(f"{len(fails)} FAIL: {fails}")
        return 1
    print("ALLE CHECKS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
