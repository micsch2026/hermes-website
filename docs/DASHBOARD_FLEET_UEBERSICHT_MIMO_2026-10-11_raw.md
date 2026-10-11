# Unabhängige Einschätzung — Dashboard „Fleet-Übersicht"

## 1. Module (oben → unten)

1. **Lage-Zeile (1 Zeile):** Ampel ROT + „7 Findings, 2 Bots blockiert" + Timestamp der Daten. Link zum Kommandocenter — keine zweite Findings-Liste.
2. **„Jetzt zu tun" (Top-3-Empfehlungen)** — bewusst *über* der Performance: Der Nutzer soll handeln, nicht bewundern.
3. **Performance-Kompakt:** Equity Demo / Live / Total (EUR) + PnL 7d / 30d (EUR **und** %), Fenster-Toggle.
4. **Fleet-Matrix (Herzstück, eine Zeile je Bot):** Name · Equity · PnL 30d · Sparkline 30d · Risk-Ampel · offene Positionen · Slot-Belegung (● belegt / ○ geplant / – frei) · Flags (Decay, Parität, Risk-Block). Sortierbar nach Dringlichkeit.
5. **Entwicklungs-Signale (Top/Bottom + Warnungen):** stärkste/schwächste Bots 7d, DD-Warnungen, Streaks, Decay-Demotes — nur mit n.
6. **Risiko & Reibung:** geblockte Entries 7d (62), Slippage median/p90, Korrelations-/Cluster-Warnungen.
7. **Shadow-Kontext (1–2 Zeilen):** 782 Trades/30d, netto −778 EUR — ehrlich zeigen, dass Strategie-Entwicklung kostet. Kein Ranking-Detail.
8. **Missionen/Wochenbericht:** 1 Zeile + Link.

**Explizit NICHT drauf:** Equity-Charts je Bot, Heatmap (beides Kommandocenter), Trade-History, Slot-Texte aus dem Launcher, Advisor-Scores, Paritäts-Details, Missions-Etappen, Wochenbericht-Text. Wer das einbaut, baut Seite 2 und 3 nochmal — genau das macht den Launcher „nichtssagend".

## 2. Performance bei heterogenen Konten

- **Primär % (Rendite auf eingesetztes Kapital), sekundär EUR.** EUR allein bevorzugt Live-Messkonten falsch (2.245 vs 7.912). R-Multiples nur, **wenn** pro Trade ein definierter Risk-Betrag im Datenmodell existiert — das weiß ich nicht. *Unsicherheit: Datenlage zu „R" prüfen.*
- **Fenster:** 7d + 30d + „seit Start der aktuellen Slot-Strategie". Warum letzteres: Rotation zerhackt die Bot-Historie; eine kumulierte „Bot-Gesamtrendite" ist wegen Strategiewechsel nicht aussagekräftig und widerspricht der Evidenz-Doktrin.
- **„Zu wenig Daten":** ab n < 20 Trades (oder < 5 Handelstage) Zahl in Grau, statt Win-Rate „–", Tooltip „n=6, Stichprobe". Sparkline mit gestricheltem Randbereich. Neue Slots: Label „neu (n=3)". *Unsicherheit: Schwellenwert 20/30/50 ist eine Produktsache — ich würde 20 nehmen, konservativ sichtbar.*
- **Kein Gesamtscore.** Demo und Live getrennt zeichnen (andere Beteiligungsquote/Ernsthaftigkeit), Total nur als Summenzeile.

## 3. Aktuelle Entwicklung ohne Overfit

Zeigbar nur mit Evidenz:
- **Trend:** 7d-Rate vs 30d-Rate (Vergleich zweier realer Fenster, keine Prognose).
- **Drawdown:** aktuell vom lokalen Hoch + Zeit im DD. Belastbar ab wenigen Trades.
- **Decay:** Flag mit Datum und Auslöser (Quelle: eigene Decay-Erkennung) — das ist die ehrlichste „Entwicklungs"-Aussage im System.
- **Streak:** erst ab 5 Trades, als Rohzahl („3 Verlusttrades, n=…"), nicht als „schlechte Laune"-Ampel.
- **Korrelation/Cluster:** Warnung, kein Trend.

Nicht zeigen: Momentum, „gute/schlechte Phase", anything unter n=10 Trades. Lieber „keine Evidenz" ausgeben — das ist ein Feature.

## 4. 10 Empfehlungen → 1–3 Zeilen

Cluster nach **Objekt** (Bot/Slot), nicht nach Quelle. Priorisierung strikt:
(a) blockiert Echtgeld/Handel (Parität, Risk-Guard) → (b) aktiver Kapitalverlust (Decay, DD) → (c) Optimierung (Advisor).

Zeilenformat:
> **bot1 · Strategie X ziehen** — Risk-Level 2/3, DD 12 % · Quelle: Risk-Guard · *Vorschlag, offen*
> **bot9 · Echtgeld gesperrt** — Paritätsabweichung seit 14:02 · *Aktion nötig*
> **+ 7 weitere → Supervisor**

Formulierung „Vorschlag/Empfehlung, Status offen", nie „wird ausgeführt" oder Auto-Buttons. Begründung = Datenwert, nicht Adjektiv. *Unsicherheit: können Aktionen vom Dashboard ausgelöst werden? Wenn nein, reiner Link-Text.*

## 5. Drei typische Fehler + der Kniff

1. **Hierarchielosigkeit:** jede Zahl gleich groß → Wand aus KPIs, die nichts priorisiert.
2. **Scheinpräzision:** Aggregatzahlen ohne Basis (Kapital, Fenster, n) — erzeugt Vertrauen ohne Evidenz.
3. **Selbstbelohnungs-Charts:** Equity-Kurven, die gut aussehen und keine Entscheidung erfordern.

**Kniff:** Jede Zeile beantwortet genau eine von drei Fragen — *Handeln / Beobachten / Nichts tun*. Sortierung nach Dringlichkeit, eine sichtbare Aktionsspalte, negative Zustände ehrlich ausgesprochen. Dann ist das Dashboard ein Werkzeug; ohne das ist es ein Poster.