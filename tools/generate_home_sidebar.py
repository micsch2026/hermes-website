#!/usr/bin/env python3
"""Generiert den "Bot-Fleet"-Sidebar-Block der Homepage DYNAMISCH aus
shadow_portfolio.json (strategy_id, desc.tag, is_live/role) statt der
hardcoded Juli-Karten (fix 2026-09-17: bot9/bot10 fehlten, Labels stale).

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

def num(k):
    try:
        return int(k.replace("bot", ""))
    except ValueError:
        return 99

def label(k):
    return f"Bot #{num(k)}"

order = sorted(bots.keys(), key=num)
live = [k for k in order if bots[k].get("is_live")]
demo = [k for k in order if not bots[k].get("is_live")]

def card(k, b):
    sid = b.get("strategy_id") or "?"
    tag = (b.get("desc") or {}).get("tag") or (b.get("strategy_name") or "")[:34]
    role = "LIVE" if b.get("is_live") else "Demo"
    icon = "shield" if b.get("is_live") else "trending-up"
    dot = ' <span style="color:#ff6b6b;font-weight:700">●</span>' if b.get("is_live") else ""
    return (f'          <a href="/{k}" class="quick-link">\n'
            f'            <i data-lucide="{icon}" class="quick-link-icon" style="width:28px;height:28px"></i>\n'
            f'            <span class="quick-link-label">{label(k)}{dot}</span>\n'
            f'            <span class="quick-link-desc">#{sid} · {tag} · {role}</span>\n'
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
print(f"✓ Sidebar generiert: {len(live)} LIVE + {len(demo)} DEMO Bots ({', '.join(order)})")
