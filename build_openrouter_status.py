#!/usr/bin/env python3
"""build_openrouter_status.py — Datenlayer der /supervisor-Sektion „LLM-Budget".

Liest den OPENROUTER_API_KEY aus einer env-Datei, ruft die OpenRouter-API
(GET https://openrouter.ai/api/v1/credits und GET https://openrouter.ai/api/v1/key
mit Header Authorization: Bearer <key>), fuehrt eine Snapshot-Historie (JSONL)
und schreibt atomar api/openrouter/status.json (Schema openrouter_v1).

stdlib-only. Kein LLM. Netz nur im echten Lauf (Tests injizieren fetch).
ENV-Overrides: OPENROUTER_ENV_FILE, OPENROUTER_HISTORY, OPENROUTER_OUT,
OPENROUTER_TIMEOUT_S (default 20).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE = Path(__file__).resolve().parent
DEFAULT_ENV = Path("/root/.hermes/.env")
DEFAULT_HISTORY = Path.home() / ".hermes/reports/openrouter/usage_history.jsonl"
DEFAULT_OUT = SITE / "api/openrouter/status.json"

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
KEY_URL = "https://openrouter.ai/api/v1/key"

MAX_POINTS = 20000          # Obergrenze der persistierten Historie
DOWNSAMPLE_LIMIT = 1500     # Obergrenze der an die Seite ausgelieferten Punkte
HEARTBEAT_S = 3600          # Mindestabstand fuer einen Punkt ohne Wertaenderung
SCHEMA = "openrouter_v1"


def _read_key(env_file: Path) -> str | None:
    """OPENROUTER_API_KEY aus einer env-Datei; Kommentarzeilen werden ignoriert."""
    try:
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                if line.lstrip().startswith("#"):
                    continue
                if line.startswith("OPENROUTER_API_KEY"):
                    parts = line.split("=", 1)
                    if len(parts) != 2:
                        continue
                    return parts[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _get_json(url: str, key: str, timeout: int) -> dict:
    """Ein GET mit Bearer-Auth; Klartext-Errors (HTTP-Status bzw. Netz)."""
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "hermes-supervisor/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} bei {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Netzwerkfehler bei {url}: {e.reason}") from e
    except OSError as e:
        raise RuntimeError(f"Netzwerkfehler bei {url}: {e}") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        raise RuntimeError(f"Ungueltiges JSON von {url}") from e


def _num(obj: dict, *keys) -> float:
    """Erste vorhandene Zahl der keys als float; fehlend/None -> 0.0."""
    for k in keys:
        v = obj.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return 0.0


def fetch_snapshot(key: str, timeout: int) -> dict:
    """credits + key abrufen. Beide muessen klappen, sonst RuntimeError."""
    credits = _get_json(CREDITS_URL, key, timeout)
    keyinfo = _get_json(KEY_URL, key, timeout)

    cd = credits.get("data", credits) if isinstance(credits, dict) else {}
    if not isinstance(cd, dict):
        cd = {}
    kd = keyinfo.get("data", keyinfo) if isinstance(keyinfo, dict) else {}
    if not isinstance(kd, dict):
        kd = {}

    return {
        "credits": {
            "total_credits": _num(cd, "total_credits", "totalCredits"),
            "total_usage": _num(cd, "total_usage", "totalUsage"),
        },
        "key": {
            "usage_daily": _num(kd, "usage_daily"),
            "usage_weekly": _num(kd, "usage_weekly"),
            "usage_monthly": _num(kd, "usage_monthly"),
        },
    }


def _load_history(path: Path) -> list[dict]:
    """JSONL-Historie; ungueltige Zeilen bzw. Eintraege werden uebersprungen."""
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                try:
                    out.append({
                        "ts": float(e["ts"]),
                        "iso": e.get("iso"),
                        "credits": float(e["credits"]),
                        "used": float(e["used"]),
                        "remaining": float(e["remaining"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue
    except OSError:
        return out
    return out


def _should_append(hist: list[dict], point: dict) -> bool:
    """True bei Wertaenderung oder wenn der Stunden-Heartbeat erreicht ist."""
    if not hist:
        return True
    last = hist[-1]
    if point["used"] != last["used"]:
        return True
    return point["ts"] - last["ts"] >= HEARTBEAT_S


def _downsample(entries: list, limit: int = DOWNSAMPLE_LIMIT) -> list:
    """Auf <= limit+8 Punkte reduzieren; erster/letzter + globales Min/Max bleiben."""
    n = len(entries)
    if n <= limit:
        return list(entries)
    buckets = max(1, limit // 2)
    size = max(1, math.ceil(n / buckets))
    out = [entries[0]]
    mid = entries[1:-1]
    for i in range(0, len(mid), size):
        chunk = mid[i:i + size]
        if not chunk:
            continue
        mn = min(range(len(chunk)), key=lambda j: chunk[j][1])
        mx = max(range(len(chunk)), key=lambda j: chunk[j][1])
        for j in sorted({mn, mx}):
            out.append(chunk[j])
    out.append(entries[-1])
    return out


def _atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _write_history(path: Path, hist: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for e in hist:
            fh.write(json.dumps({
                "ts": e["ts"], "iso": e["iso"], "credits": e["credits"],
                "used": e["used"], "remaining": e["remaining"],
            }, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _resolve(arg, env_name: str, default: Path) -> Path:
    if arg is not None:
        return Path(arg)
    v = os.environ.get(env_name)
    return Path(v) if v else default


def _timeout(arg) -> int:
    if arg is not None:
        return int(arg)
    v = os.environ.get("OPENROUTER_TIMEOUT_S")
    try:
        return int(v)
    except (TypeError, ValueError):
        return 20


def _fail_soft(out_path: Path, now_iso: str, err: str) -> int:
    """Fetch-Fehler: vorhandenes Dokument nur markieren, sonst Minimal-Dokument."""
    prev = None
    try:
        with open(out_path, encoding="utf-8") as fh:
            prev = json.load(fh)
        if not isinstance(prev, dict):
            prev = None
    except (OSError, ValueError):
        prev = None

    if prev is None:
        doc = {
            "schema": SCHEMA,
            "generated_at": now_iso,
            "fetched_at": None,
            "fetch_ok": False,
            "fetch_error": err,
            "balance": None,
            "spend": None,
            "history": [],
            "history_n": 0,
            "history_first_iso": None,
            "history_last_iso": None,
        }
    else:
        doc = prev
        doc["schema"] = doc.get("schema", SCHEMA)
        doc["generated_at"] = now_iso
        doc["fetch_ok"] = False
        doc["fetch_error"] = err

    _atomic_write(out_path, doc)
    print(f"FETCH-FEHLER: {err}", file=sys.stderr)
    return 1


def build(fetch=fetch_snapshot, env_file=None, history_path=None, out_path=None,
          timeout=None, now_ts=None) -> int:
    """Ein Zyklus: Fetch -> Snapshot -> Historie -> status.json. 0 ok / 1 Fehler."""
    env_file = _resolve(env_file, "OPENROUTER_ENV_FILE", DEFAULT_ENV)
    history_path = _resolve(history_path, "OPENROUTER_HISTORY", DEFAULT_HISTORY)
    out_path = _resolve(out_path, "OPENROUTER_OUT", DEFAULT_OUT)
    timeout = _timeout(timeout)
    now = float(now_ts) if now_ts is not None else time.time()
    now_iso = datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds")

    key = _read_key(env_file)
    if not key:
        return _fail_soft(out_path, now_iso, "OPENROUTER_API_KEY nicht gefunden")

    try:
        snap = fetch(key, timeout)
    except Exception as e:  # noqa: BLE001 - bewusst fail-soft, Meldung nach stderr
        return _fail_soft(out_path, now_iso, str(e))

    total_credits = float(snap["credits"]["total_credits"])
    total_usage = float(snap["credits"]["total_usage"])
    remaining = total_credits - total_usage
    daily = float(snap["key"].get("usage_daily") or 0.0)
    weekly = float(snap["key"].get("usage_weekly") or 0.0)
    monthly = float(snap["key"].get("usage_monthly") or 0.0)

    point = {
        "ts": now, "iso": now_iso, "credits": total_credits,
        "used": total_usage, "remaining": remaining,
    }
    hist = _load_history(history_path)
    if _should_append(hist, point):
        hist = (hist + [point])[-MAX_POINTS:]
        _write_history(history_path, hist)

    used_pct = round(100 * total_usage / total_credits, 1) if total_credits > 0 else None
    burn = round(weekly / 7, 4)
    runway = round(remaining / burn, 1) if burn > 0 else None

    entries = [[round(e["ts"], 1), round(e["remaining"], 6), round(e["used"], 6)]
               for e in hist]
    chart = _downsample(entries, DOWNSAMPLE_LIMIT)

    doc = {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "fetched_at": now_iso,
        "fetch_ok": True,
        "fetch_error": None,
        "balance": {
            "total_credits": total_credits,
            "total_usage": total_usage,
            "remaining": remaining,
            "used_pct": used_pct,
        },
        "spend": {
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "burn_7d_per_day": burn,
            "runway_days": runway,
        },
        "history": chart,
        "history_n": len(hist),
        "history_first_iso": hist[0]["iso"] if hist else None,
        "history_last_iso": hist[-1]["iso"] if hist else None,
    }
    _atomic_write(out_path, doc)
    print(f"OK {out_path} ({out_path.stat().st_size} bytes) "
          f"remaining={remaining:.2f} used={total_usage:.2f} points={len(hist)}")
    return 0


def main() -> int:
    return build()


if __name__ == "__main__":
    sys.exit(build())
