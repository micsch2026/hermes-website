#!/usr/bin/env python3
"""
smart_rebuild.py — Site-Rebuilder mit Change-Detection.

Prueft ob Quelldaten neuer sind als der letzte erfolgreiche Build.
Nur bei Aenderung wird neu gebaut (mtime-Vergleich).
Zusaetzlich Staleness-Guard (FIX 2026-10-22): ist der letzte ERFOLGREICHE Build
aelter als max_staleness_hours, wird auch OHNE Quellaenderung neu gebaut —
sonst skippt ein statisches src/ ewig und der Trading-Watchdog meldet ab 26h
"Build stale" (site: 24h-Limit < 26h-Watchdog-Frist).
Verhindert parallele Ausfuehrungen via PID-File.

Targets:
  data         — build_data_status.py (alle 60 Min)
  site         — build.py HTML rebuild (alle 6h)
  all          — Alle Targets mit Change-Detection

Usage:
    python3 smart_rebuild.py data                  # Nur Data-Pipeline rebuilden
    python3 smart_rebuild.py site                  # Full Site rebuild
    python3 smart_rebuild.py all                   # Alles (mit Change-Detection)
    python3 smart_rebuild.py backtest --force      # Erzwingt Rebuild
    python3 smart_rebuild.py all --dry-run         # Nur pruefen, nicht bauen
    python3 smart_rebuild.py --health              # Health-Check: Outputs frisch?
"""

import fcntl
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ────────────────────────────────────────────

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = "/root/fx-bot/logs"
STATE_FILE = os.path.join(SITE_DIR, ".rebuild_state.json")
PID_FILE = os.path.join(SITE_DIR, ".rebuild.pid")

# Logging
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "rebuild.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("smart_rebuild")

# ── Target Definitions ───────────────────────────────────────

TARGETS = {
    "data": {
        "watch_dirs": [
            "/root/trading/data",
        ],
        "watch_files": [
            "/root/fx-bot/logs/fetch.log",
        ],
        "build_cmd": [sys.executable, "build_data_status.py"],
        "build_cwd": SITE_DIR,
        "output": "/root/.hermes/site/api/data/pipeline_status.json",
        "timeout": 120,
        "max_staleness_hours": 2,
    },
    "site": {
        "watch_dirs": [
            os.path.join(SITE_DIR, "src"),
        ],
        "watch_files": [
            os.path.join(SITE_DIR, "build.py"),
        ],
        "build_cmd": [sys.executable, "build.py"],
        "build_cwd": SITE_DIR,
        "output": os.path.join(SITE_DIR, "_build", "index.html"),
        "timeout": 60,
        "max_staleness_hours": 24,
    },
}


# ── Locking ──────────────────────────────────────────────────

class PidLock:
    """Prevent concurrent rebuilds via flock."""

    def __init__(self, path):
        self.path = path
        self.fd = None

    def acquire(self):
        """Try to acquire lock. Returns True on success."""
        self.fd = open(self.path, "w")
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd.write(str(os.getpid()))
            self.fd.flush()
            return True
        except (IOError, OSError):
            self.fd.close()
            self.fd = None
            return False

    def release(self):
        if self.fd:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                self.fd.close()
            except Exception:
                pass
            self.fd = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Another rebuild is already running")
        return self

    def __exit__(self, *args):
        self.release()


# ── Helpers ──────────────────────────────────────────────────

def get_max_mtime(cfg):
    """Find the newest mtime across all watched files and directories."""
    max_mtime = 0
    paths = []

    for f in cfg.get("watch_files", []):
        if os.path.exists(f):
            paths.append(f)

    for d in cfg.get("watch_dirs", []):
        if os.path.isdir(d):
            for root, _, files in os.walk(d):
                for fname in files:
                    if fname.endswith(".json") or fname.endswith(".log"):
                        paths.append(os.path.join(root, fname))

    for p in paths:
        try:
            mt = os.path.getmtime(p)
            if mt > max_mtime:
                max_mtime = mt
        except OSError:
            pass

    return max_mtime


def load_state():
    """Load persisted build state (last mtime per target)."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """Persist build state atomically."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ── Core Build Logic ─────────────────────────────────────────

def rebuild_decision(name, cfg, state, now_epoch=None, current_mtime=None):
    """Entscheidet, ob gebaut wird -> (should_build, reason).

    Trigger (FIX 2026-10-22): (a) Quell-mtime neuer als letzter Build;
    (b) Staleness-Guard: letzter erfolgreicher Build >= max_staleness_hours her
    (auch OHNE Quellaenderung). Ohne parsebaren last_build-Zeitstempel wird
    einmal gebaut (State-Refresh), danach greift der Guard normal.
    """
    if now_epoch is None:
        now_epoch = time.time()
    if current_mtime is None:
        current_mtime = get_max_mtime(cfg)
    tstate = state.get(name, {})
    last_mtime = tstate.get("mtime", 0)

    if current_mtime > last_mtime:
        return True, (f"changes detected (mtime {last_mtime:.0f} -> {current_mtime:.0f}, "
                      f"delta={format_duration(current_mtime - last_mtime)}), rebuilding...")

    max_age = cfg.get("max_staleness_hours")
    if max_age is not None:
        lb = tstate.get("last_build")
        if not lb:
            return True, "no last-build timestamp — rebuilding once to refresh state"
        try:
            dt = datetime.fromisoformat(lb)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (now_epoch - dt.timestamp()) / 3600.0
        except ValueError:
            return True, "unparsable last-build timestamp — rebuilding once to refresh state"
        if age_h >= max_age:
            return True, (f"no changes, but stale (last build {age_h:.1f}h ago >= "
                          f"{max_age}h limit), rebuilding...")

    return False, f"no changes detected (mtime={current_mtime:.0f})"


def run_build(name, cfg, force=False):
    """Check for changes/staleness and run build if needed. Returns (built, duration_s, error)."""
    current_mtime = get_max_mtime(cfg)
    state = load_state()
    last_mtime = state.get(name, {}).get("mtime", 0)

    if not force:
        should, reason = rebuild_decision(name, cfg, state, current_mtime=current_mtime)
        if not should:
            log.info(f"{name}: {reason}, skipping")
            return False, 0, None
        log.info(f"{name}: {reason}")
    else:
        log.info(f"{name}: forced rebuild")

    start = time.monotonic()
    try:
        result = subprocess.run(
            cfg["build_cmd"],
            cwd=cfg.get("build_cwd", SITE_DIR),
            capture_output=True,
            text=True,
            timeout=cfg.get("timeout", 120),
        )
        duration = time.monotonic() - start

        if result.returncode == 0:
            log.info(f"{name}: build OK in {format_duration(duration)}")
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n")[-5:]:
                    log.info(f"  {line}")
            state[name] = {
                "mtime": current_mtime,
                "last_build": datetime.now(timezone.utc).isoformat(),
                "status": "ok",
                "duration_s": round(duration, 2),
            }
            save_state(state)
            return True, duration, None
        else:
            err_msg = result.stderr[-500:] if result.stderr else "unknown"
            log.error(f"{name}: build FAILED (exit {result.returncode}) in {format_duration(duration)}")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-10:]:
                    log.error(f"  {line}")
            # Don't update mtime on failure — retry next cycle
            state[name] = {
                "mtime": last_mtime,
                "last_build": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "error": err_msg,
                "duration_s": round(duration, 2),
            }
            save_state(state)
            return False, duration, err_msg

    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        timeout_s = cfg.get("timeout", 120)
        log.error(f"{name}: build TIMEOUT after {timeout_s}s")
        state[name] = {
            "mtime": last_mtime,
            "last_build": datetime.now(timezone.utc).isoformat(),
            "status": "timeout",
            "timeout_s": timeout_s,
        }
        save_state(state)
        return False, duration, f"timeout after {timeout_s}s"

    except Exception as e:
        duration = time.monotonic() - start
        log.error(f"{name}: build EXCEPTION: {e}")
        state[name] = {
            "mtime": last_mtime,
            "last_build": datetime.now(timezone.utc).isoformat(),
            "status": "exception",
            "error": str(e),
        }
        save_state(state)
        return False, duration, str(e)


# ── Health Check ─────────────────────────────────────────────

def health_check():
    """Check if all build outputs are fresh."""
    now = time.time()
    state = load_state()
    issues = []
    ok = []

    for name, cfg in TARGETS.items():
        output = cfg.get("output", "")
        max_age_hours = cfg.get("max_staleness_hours", 24)

        # Check output file existence
        if not output or not os.path.exists(output):
            issues.append(f"{name}: output MISSING ({output})")
            continue

        # Check output freshness
        output_mtime = os.path.getmtime(output)
        age_hours = (now - output_mtime) / 3600

        if age_hours > max_age_hours:
            issues.append(
                f"{name}: output STALE ({format_duration(now - output_mtime)} old, "
                f"limit={max_age_hours}h)"
            )
        else:
            ok.append(
                f"{name}: OK (age={format_duration(now - output_mtime)}, "
                f"limit={max_age_hours}h)"
            )

        # Check last build status
        target_state = state.get(name, {})
        if target_state.get("status") == "failed":
            issues.append(
                f"{name}: last build FAILED at {target_state.get('last_build', '?')}"
            )
        elif target_state.get("status") == "timeout":
            issues.append(
                f"{name}: last build TIMED OUT at {target_state.get('last_build', '?')}"
            )

    # Print report
    for line in ok:
        log.info(f"  OK: {line}")
    for line in issues:
        log.warning(f"  ISSUE: {line}")

    return len(issues) == 0


# ── Main ─────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target_name = sys.argv[1]
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    # Health check mode
    if target_name == "--health":
        healthy = health_check()
        sys.exit(0 if healthy else 1)

    if target_name == "all":
        targets = TARGETS
    elif target_name in TARGETS:
        targets = {target_name: TARGETS[target_name]}
    else:
        log.error(f"Unknown target: {target_name}")
        log.info(f"Available: {', '.join(TARGETS.keys())}, all, --health")
        sys.exit(1)

    # Acquire lock to prevent concurrent runs
    try:
        with PidLock(PID_FILE):
            total_start = time.monotonic()
            results = {}

            for name, cfg in targets.items():
                if dry_run:
                    mtime = get_max_mtime(cfg)
                    state = load_state()
                    should, reason = rebuild_decision(name, cfg, state, current_mtime=mtime)
                    log.info(f"{name}: would_rebuild={should} — {reason}")
                    results[name] = {"would_rebuild": should, "mtime": mtime}
                else:
                    built, duration, error = run_build(name, cfg, force=force)
                    results[name] = {
                        "built": built,
                        "duration_s": round(duration, 2),
                        "error": error,
                    }

            total_duration = time.monotonic() - total_start

            if not dry_run:
                # Summary
                built_count = sum(1 for r in results.values() if r.get("built"))
                failed_count = sum(1 for r in results.values() if r.get("error"))
                log.info(
                    f"Done. {built_count}/{len(targets)} targets rebuilt, "
                    f"{failed_count} errors, total={format_duration(total_duration)}"
                )

                if failed_count > 0:
                    for name, r in results.items():
                        if r.get("error"):
                            log.error(f"  FAILED: {name}: {r['error']}")
                    sys.exit(1)

    except RuntimeError as e:
        log.warning(f"Skipping: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
