#!/usr/bin/env python3
"""Generiert den "Bot-Fleet"-Sidebar-Block der Homepage DYNAMISCH aus
shadow_portfolio.json (strategy_id, desc.tag, is_live/role) statt der
hardcoded Juli-Karten (fix 2026-09-17: bot9/bot10 fehlten, Labels stale).

Multibot-Kennzeichnung (2026-09-28): Bots mit Rotations-Slots
(bot_rotation_slots nicht leer) bekommen ein MULTI-Chip + Slot-Zeile
(z.B. "s372 #372 + s534 #534 + srot → #663"). Quelle bleibt
shadow_portfolio.json — kein Hardcode, keine Extra-Config.

Läuft manuell oder vor dem Site-Build:  python3 generate_home_sidebar.py
Quelle der Wahrheit: /root/.hermes/site/api/strategy-lab/shadow_portfolio.json
(Refresh: /root/fx-bot/src/shadow_portfolio_builder.py, 15-Min-Takt).
"""
import json
import re

INDEX = "/root/.hermes/site/src/content/index.html"
PORT = "/root/.hermes/site/api/strategy-lab/shadow_portfolio.json"

sp = json.load(open(PORT))
bots = sp.get("bots", {})
rot_map = sp.get("bot_rotation_slots") or {}
strategies = sp.get("strategies") or []

def num(k):
    try:
        return int(k.replace("bot", ""))
    except ValueError:
        return 99

def label(k):
    return f"Bot #{num(k)}"

# Fixe Slots je Bot aus strategies[].deployed_bots (slot_id + Strategie-ID)
fixed_slots = {}
for s in strategies:
    for db in (s.get("deployed_bots") or []):
        if isinstance(db, dict) and db.get("bot"):
            fixed_slots.setdefault(db["bot"], []).append((db.get("slot"), s.get("id")))
for _k in fixed_slots:
    fixed_slots[_k].sort(key=lambda x: (x[0] or ""))

order = sorted(bots.keys(), key=num)
live = [k for k in order if bots[k].get("is_live")]
demo = [k for k in order if not bots[k].get("is_live")]

def slot_line(k):
    """Slot-Zusammenfassung für Multibots: 's372 #372 + s534 #534 + srot → #663'."""
    parts = []
    for slot, sid in fixed_slots.get(k, []):
        if slot:
            parts.append(f"{slot} #{sid}" if sid is not None else slot)
    for rs in (rot_map.get(k) or []):
        txt = rs.get("slot_id") or "rot"
        ch = rs.get("challenge") or {}
        if ch.get("candidate") is not None:
            txt += f" → #{ch['candidate']}"
        elif rs.get("holder") is not None:
            txt += f" → #{rs['holder']}"
        parts.append(txt)
    return " + ".join(parts)

def card(k, b):
    sid = b.get("strategy_id") or "?"
    tag = (b.get("desc") or {}).get("tag") or (b.get("strategy_name") or "")[:34]
    role = "LIVE" if b.get("is_live") else "Demo"
    is_multi = bool(rot_map.get(k))
    icon = "shield" if b.get("is_live") else ("layers" if is_multi else "trending-up")
    dot = ' <span style="color:#ff6b6b;font-weight:700">●</span>' if b.get("is_live") else ""
    chip = (' <span class="multi-chip" title="Multibot — mehrere Strategie-Slots + Rotation">MULTI</span>'
            if is_multi else "")
    if is_multi:
        desc = f"{slot_line(k)} · {role}"
    else:
        desc = f"#{sid} · {tag} · {role}"
    return (f'          <a href="/{k}" class="quick-link">\n'
            f'            <i data-lucide="{icon}" class="quick-link-icon" style="width:28px;height:28px"></i>\n'
            f'            <span class="quick-link-label">{label(k)}{chip}{dot}</span>\n'
            f'            <span class="quick-link-desc">{desc}</span>\n'
            f'          </a>')

cards = []
if live:
    cards.append('          <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.05em;color:var(--dim,#8892a8);margin:0.35rem 0 0.2rem">🔴 ECHTGELD (MESSKONTEN)</div>')
    cards.extend(card(k, bots[k]) for k in live)
if demo:
    cards.append('          <div style="font-size:0.68rem;font-weight:700;letter-spacing:0.05em;color:var(--dim,#8892a8);margin:0.35rem 0 0.2rem">🧪 DEMO (ANSATZ-MATRIX)</div>')
    cards.extend(card(k, bots[k]) for k in demo)

section = ('      <!-- Bot-Fleet (GENERIERT von tools/generate_home_sidebar.py — nicht handeditieren) -->\n'
           '      <section aria-label="Bot-Fleet">\n'
           '        <div class="section-title"><i data-lucide="radio" style="width:14px;height:14px"></i> Bot-Fleet</div>\n'
           '        <div class="section-grid">\n' + "\n".join(cards) + '\n        </div>\n      </section>')

html = open(INDEX).read()
new_html, n = re.subn(r'      <!-- Live Bots -->\n      <section aria-label="Live Bots">.*?</section>',
                      lambda m: section, html, count=1, flags=re.S)
if n != 1:
    # Fallback: schon generierter Block → ersetzen
    new_html, n = re.subn(r'      <!-- Bot-Fleet \(GENERIERT.*?</section>',
                          lambda m: section, html, count=1, flags=re.S)
if n != 1:
    raise SystemExit("❌ Sidebar-Block nicht gefunden!")
open(INDEX, "w").write(new_html)
multi = [k for k in order if rot_map.get(k)]
print(f"✓ Sidebar generiert: {len(live)} LIVE + {len(demo)} DEMO Bots ({', '.join(order)})")
print(f"  MULTI markiert: {', '.join(multi) if multi else '—'}")
