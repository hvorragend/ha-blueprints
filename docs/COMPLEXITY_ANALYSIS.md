# CCA-Blueprint: Komplexitäts- und Logikanalyse (Stand 2026-07-01)

Analysebasis: `blueprints/automation/cover_control_automation.yaml`, 7.794 Zeilen,
Version 2026.06.28 V3 (Commit b1b6e97). Zeilennummern beziehen sich auf diesen Stand.

**Kurzfassung:** Die Blueprint ist funktional solide durchdacht — die
`effective_state`-Kaskade, das v6-Helper-Schema und die Trigger-Hygiene sind gut.
Sie trägt aber drei große Komplexitätslasten: (1) ~55–60 % der Input-Sektion sind
Beschreibungsprosa, (2) die Prioritätskaskade ist in den Force-Handlern dreifach als
choose-Ketten von Hand nachgebaut statt aus `effective_state` abgeleitet, und
(3) das Drive-Idiom (Delay → Before-Action → Move → Tilt → After-Action) ist ~15×
inline kopiert. Dazu wurden zwei bestätigte Hänger-Bugs gefunden (fehlende
Auffangzweige, die Pending-Zustände festfressen) sowie ein Dutzend kleinerer
Auffälligkeiten. Realistisches Einsparpotenzial ohne Verhaltensänderung:
~2.500–3.500 Zeilen.

---

## 1. Ablaufübersicht — alle Pfade von Trigger bis Endaktion

**Vorlauf bei jedem Trigger** (läuft immer, vor dem Haupt-choose):

1. Helper-Init/Reparatur (4214)
2. v5→v6-Migration (4254)
3. Forecast-Load bei `^(t_shading_start|t_open|t_calendar_event_start)` (4271)
4. Kalender-Load (4316)
5. ~650 Zeilen Recalc-Variablen ohne Guard (4344–4998)
6. Helper-Pflichtvalidierung mit `stop` (5005)
7. Haupt-choose (5060)

**Haupt-choose, 12 Handler** (`⛭` = Fahrt, `✎` = nur Helper-Update):

| # | Handler (Zeile) | Trigger | Pfade |
|---|---|---|---|
| 1 | Opening (5070) | `t_open_*`, `t_calendar_event_*` | already-open ✎ · shading-detected ⛭ · pending-skip ✎ · pending-arm ✎ (#555) · normal-open ⛭ · default ✎ |
| 2 | Closing (5252) | `t_close_*`, `t_calendar_event_*` | lockout ✎ · tilted→vent ⛭ · already-closed ✎ · shaded-blocked ✎ · normal-close ⛭ |
| 3 | Shading-Start (5434) | `t_shading_start_pending_1–7`, `_execution`, `t_open_1` | cancel-end-pending ✎ · arm-pending ✎ · Execution: lockout ✎ / drive ⛭ / save-for-future ✎ / 3× retry-blocked ✎ · 3× retry-not-met ✎ · default (nur stop) |
| 4 | Shading-Tilt (5759) | `t_shading_tilt_1–4` | ein linearer Pfad ⛭ (nur Tilt) |
| 5 | Shading-End (5794) | `t_shading_end_pending_1–7`, `_execution` | arm-pending ✎ · tilt-only ⛭ · lockout ✎ · vent ⛭ · move-open ⛭ · retry ✎ · abort ✎ · stale-cleanup ✎ (#395) |
| 6 | Contact (6081) | `t_contact_*_changed` | opened→lockout ⛭ · opened-sync ✎ · tilted→vent ⛭ · tilted-sync ✎ · closed→shading ⛭ / →open ⛭ / →close ⛭ |
| 7 | Resident (6361) | `t_resident_update` | Leaving: vent-full/vent-tilt/shaded/open/close ⛭ + default ✎ · Arriving: lockout ✎ / vent-hold ⛭ / close ⛭ + default ✎ |
| 8 | Force enabled (6600) | `t_force_enabled_*` | 4× identisches Skelett: `frc` setzen + ⛭ |
| 9 | Force-Pause-Ende (6718) | `t_force_pause_disabled` | 10 Zweige = Hand-Switch über `effective_state`, alle ⛭ |
| 10 | Force disabled (6890) | `t_force_disabled_*` | not-active-stop · 4× Last-Wins ⛭ · Recovery: 5 Zweige (Hand-Nachbau der Kaskade) ⛭ · 2× nur-`frc:non` ✎ |
| 11 | Manual (7208) | `t_manual_position`(×3), `t_manual_tilt` | 6 Klassifikationszweige ✎ + `auto_manual_action` |
| 12 | Reset (7399/7452) | `t_reset_*`, `t_shading_reset` | Position-Restore open/close ✎ · default `man:0` ✎ · Mitternachtsreset ✎ |
| — | default (7480) | alles Übrige | ~40 Config-Checks (~312 Zeilen) + „No branch matched“-Log |

---

## 2. Komplexitäts-Befund

**Kennzahlen:** 132 Inputs in 16 Sektionen (2.726 Zeilen) · 96 `trigger_variables`
+ ~85 `variables` ≈ 180 Variablen · 48 Trigger-Einträge (45 IDs) · 113
`choose:`-Blöcke, 94 Aliase · maximale Verschachtelungstiefe 5–6 (Shading-Start:
`choose→if→choose→if→choose`) · längste Handler: Shading-Start 320 Zeilen/13
Zweige, Force-disabled 313 Zeilen.

**Wo die Komplexität unnötig ist:**

1. **Doku im Code (~1.400–1.700 Zeilen):** Über die Hälfte der Input-Sektion sind
   `<details>`-HTML-Blöcke und Erklärprosa (allein `auto_options` ~62 Zeilen
   Beschreibung). Gewachsene Inline-Hilfe, keine Logik.
2. **Kaskade dreifach implementiert:** `effective_state` (3293) beantwortet „wohin
   soll das Cover?“ bereits vollständig. Handler 9 (10 Zweige) und die Recovery in
   Handler 10 (5 Zweige) bauen dieselbe Entscheidung als choose-Ketten nach — mit
   eigener, leicht abweichender Reihenfolge. In Handler 9 sind die Zweige 1–4
   (`frc==X`-Varianten) byte-identisch zu den Zweigen 6–9 bis auf die engere
   Bedingung — tote Differenzierung (6724 vs. 6804 verifiziert).
3. **Drive-Wrapper ~15× kopiert:** `if force_allows_X → delay(random) →
   before-action → *cover_move → *tilt_move → after-action → *helper_update`
   steht inline in H1-b2/b5, H2-b2/default, H3-c2, H5-e4/e5, H6-f1/f3/f5/f6/f7,
   H7 (5×), H8 (4×), H9 (10×), H10 (9×).
4. **Retry-Maschinerie doppelt und gespiegelt:** Shading-Start hat die Trias
   „waiting-for-window / continue / abort“ zweimal (blocked-Pfad 5637–5684,
   not-met-Pfad 5691–5750 — Unterschied nur `log_extra`), Shading-End ein drittes
   Mal (6011–6050).
5. **Variablen-Wildwuchs:** 2 tote Variablen (`helper_ts_pending_due` 3351,
   `active_force_from_sensors` 3407), ~12 Nur-einmal-Wrapper, inkonsistenter
   Zugriff (`helper_json.ts.due` 6× direkt trotz existierendem Wrapper),
   `resident_flags`-Logik in `effective_state` (3296–3299) inline dupliziert.
6. **Defensiv-Totcode:** `repeat.item if repeat is defined else ''` (6×),
   `wait.completed if wait is defined` (4100), doppelte Helper-Validierung
   (4218 = 5026; Warnzweig 5023–5040 tot, weil Init vorher repariert), doppelte
   invalid-state-Checks im Manual-Handler (7216 + je Zweig).

---

## 3. Gefundene Logikfehler

| # | Abschnitt (Zeile) | Fehler | Schwere | Konkretes Szenario |
|---|---|---|---|---|
| 1 | Shading-Start-Execution, inneres choose ohne default (5541–5633) | Wenn Bedingung erfüllt + kein Lockout, aber weder „Start Shading“-Positions-OR (5575–5585) noch „Save for future“ (5620) matcht, endet die Sequenz ohne `helper_update` und ohne `stop` → `pnd='beg'` mit abgelaufenem `ts.due` bleibt stehen; Execution-Template (3763) bleibt dauerhaft true → keine neue Flanke → Pending hängt bis Mitternachtsreset | **kritisch** | Nicht-Tilt-Cover exakt auf `shading_position` (Gleichheits-Alternative existiert nur im Tilt-Zweig 5581); oder Cover unterhalb Shading-Position mit `effective_state=='vnt'` (dritte OR-Alternative 5585 verlangt `=='opn'`) |
| 2 | Shading-End „Move cover“ (5956–6006) | `if not prevent_flags.opening_after_shading_end` ohne else → bei aktivem „Öffnen nach Beschattungsende verhindern“ folgt `stop` ohne helper_update → `pnd='end'`, `shd=1` bleiben; Execution-Template dauerhaft true, neue End-Pendings blockiert → Cover hängt in Beschattung (#395-Muster) | **kritisch** | `prevent_opening_after_shading_end` konfiguriert und Tilt nicht möglich und weder Lockout (e3) noch gekipptes Fenster (e4) |
| 3 | Globales Shading-Gate (4017) | Regex deckt nur `t_shading_start_pending_[1-6]` — `_7` (3758) läuft auch bei `shd==1` durch; Arm-Zweig (5488) prüft nicht `not helper_state_shade` → kann gemerkte Beschattung (`shd=1, pnd=non`) morgens auf `shd:0, pnd:'beg'` zurücksetzen und `ts.shd` neu stempeln | mittel | „Save for future“ von gestern Abend; `_7` feuert 1 h vor Öffnungszeit bei erfüllten Bedingungen. Hinweis: Gate NICHT auf `[1-7]` erweitern — bei `shd==1`/`pnd='end'` ist `_7` der einzige Start-Trigger, der den Cancel-End-Pending-Zweig (5469) erreichen kann |
| 4 | Shading-End e4 (5920) | Operator-Präzedenz: `if_lower_enabled and current_above_ventilate or current_position == ventilate_position` = `(A and B) or C` — Gleichheits-Alternative nicht durch `if_lower_enabled` gegated; strukturgleiche Stelle im Contact-Handler (6180) ist korrekt geklammert | mittel | Cover exakt auf `ventilate_position`, `if_lower` deaktiviert |
| 5 | Restart-Verhalten der Pending-/Zeitschwellen-Template-Trigger (3763, 3896, 3915, 3960) | Template-Trigger feuern nur auf false→true-Flanke. Ist das Template beim HA-Start bereits true (Pending während Downtime fällig; Neustart nach 23:55), gibt es keine Flanke → Execution/Reset feuern nie | mittel | HA-Neustart, während `ts.due` in der Vergangenheit liegt. Bekannte HA-Einschränkung, dokumentieren |
| 6 | Reset-Handler default (7438) | `t_reset_position`, Cover weder in Open- noch Close-Position → nur `man:0`, `bas` wird nicht synchronisiert | mittel | Reset-Position = 100, Cover steht bei 60 |
| 7 | Eintrittsguard Shading-Start (5442–5445) | Bei aktiviertem Tilt ist die OR immer wahr — Guard wirkungslos; im Code als `TODO / FIXME?` markiert | gering | — |
| 8 | Regex-Tippfehler `\{s*` statt `\{\s*` (7×: 3174, 3766, 3899, 3970, 3986, 4218, 5026) | Funktioniert nur zufällig (`s*` matcht null ‚s‘) | gering | — |
| 9 | Tote Variablen (3351, 3407) | `helper_ts_pending_due` nie genutzt; `active_force_from_sensors` (~12-Zeilen-Template) nie genutzt | gering | — |
| 10 | Force-enabled-Handler ohne default (6605); Shading-End-THEN-choose ohne default für Pending-Trigger | Fall-through ohne helper_update; praktisch harmlos/unerreichbar | gering | — |
| 11 | `state_attr(sun,'azimuth'/'elevation')` ohne default (2954/2955) | `None` bei unavailable Sonnensensor → potenzielle None-Vergleiche | gering | Sonnensensor kurz unavailable |
| 12 | 3× gleiche Trigger-ID `t_manual_position` (3929/3938/3946); ID-Lücken `t_open_3`/`t_close_3`; `_end_pending_7` physisch vor `_6` | Nur Hygiene/Trace-Eindeutigkeit | gering | — |

**Geprüft und kein Fehler:** `trigger_variables` ohne `states()`-Verstöße
(Invariante 10 sauber). Der scheinbar redundante Re-Close im Closing-default wird
durch den Toleranz-Vorcheck in `&cover_move_action` (4035–4040) unterdrückt.
`mode: queued` + Delays erzeugt nur Latenz, keine Races.

---

## 4. Vereinfachungsplan (priorisiert nach Einsparung ÷ Risiko)

| Schritt | Inhalt | Einsparung | Verhaltensgleich? | Risiko |
|---|---|---|---|---|
| Fix #1, #2 | Default-/else-Zweige ergänzen | — | Bugfix | niedrig |
| Fix #3, #4, #8 | Arm-Guard, Klammerung, Regex-Tippfehler | — | Bugfix / gleich | niedrig |
| V6 | Variablen-Hygiene, Totcode | ~80–120 Z. | ja | sehr niedrig |
| V4 | Retry-Trias fusionieren (reason-Variable) | ~60 Z., 3 Zweige | ja (bis auf log_extra-Text) | niedrig |
| V7 | Boilerplate-Tails (Manual 6×, Resident 3×) | ~40 Z. | ja | niedrig |
| V1 | Force-Pause: redundante frc-Zweige 1–4 entfernen, Mapping | ~130 Z., 9 Zweige | ja (nur Trace-Alias) | niedrig |
| V3 | Drive-Wrapper-Anker für uniforme Call-Sites | ~100–130 Z. | ja | niedrig-mittel |
| V5 | Doku-Auslagerung in Handbuch (GitHub Pages), FAQ einbeziehen | ~1.500 Z. | ja (reine Doku) | UX-Entscheidung |
| V2 | Force-enabled/Last-Wins parametrisieren; Recovery gegen Kaskade abgleichen | ~170–280 Z. | verhaltensähnlich, Einzelfallabgleich | mittel |

**Bewusst NICHT umgesetzt:** Inputs zusammenlegen (bricht bestehende
Nutzer-Konfigurationen beim Blueprint-Update); Trigger zusammenlegen (Aufsplittung
ist bugfix-bedingt, Bug Pattern M; HA-Template-Trigger können keine Logik teilen).

---

## 5. Ziel-Architektur

```
┌─ Inputs (schlank, Doku extern im Handbuch)              ~1.200 Z.
├─ trigger_variables (statisch, wie bisher)                 ~180 Z.
├─ variables: EINE Wahrheitsquelle                          ~450 Z.
│    helper_json → effective_state → flags (resident/override/prevent)
├─ triggers (unverändert — Granularität ist bugfix-bedingt) ~500 Z.
├─ Anker:  &cover_move  &tilt_move  &helper_update
│          &drive_with_actions   ← NEU: das eine Fahr-Idiom
├─ Handler = dünne Intent-Schicht:                        ~1.400 Z.
│    Helper-Mutation entscheiden → Mapping(effective_state) → drive
│    Force-Handler: reine frc-Mutation + generischer Reconcile
│    Shading-Retry: EINE parametrisierte Pending-Routine
└─ default: Config-Check (unverändert)
```

Zielgröße realistisch ~4.000–4.500 Zeilen statt 7.794 — dieselben 12 Handler,
dieselben Trigger, dasselbe Helper-Schema.

---

## 6. Was gut ist und NICHT angefasst wird

- `effective_state`-Kaskade mit Live-Sensor-`win` (inkl. `is_opening_scheduled`,
  #553)
- v6-Helper-Schema mit `pnd`-Enum (Invariante 11 strukturell erzwungen)
- `helper_update`-Anker mit `ts.shd`-Guard und Preserve-Semantik
- Trigger-Hygiene: `not_to`-Filter (#550), from/to-Invalid-Guards (#505),
  aufgesplittete Azimut/Elevation-End-Trigger (Bug Pattern M)
- Dokumentierte asymmetrische Design-Entscheidungen (Opening bewahrt Pending nur
  „warranted“, Closing verwirft; Resident-Handler ohne Override-Gate;
  Mitternachtsreset-`man:0`)
- `mode: queued` + idempotente Zweige
- Testsuite (210 Tests, parsen die YAML direkt)
- Trace-Aliase + `log_extra`-Konzept

---

## 7. Umsetzungsstand (2026-07-01, CCA 2026.07.01)

Umgesetzt (je ein Commit pro Schritt, alle Tests grün):

- ✅ Fix #1 (Default im Shading-Start-Drive-choose), Fix #2 (else im
  „Move cover after shading end“), Fixes #3/#4/#8 (Arm-Guard,
  Klammerung, Regex-Tippfehler ×7)
- ✅ V6 Variablen-Hygiene — **mit einer wichtigen Korrektur:** die
  `repeat is defined`/`wait is defined`-Guards in den Anker-Bodies sind
  KEIN toter Code. Die Anker sind Werte eines `variables:`-Schritts und
  werden von HA bei jedem Lauf mitgerendert — die Guards sind tragend
  (neue Invariante 13 in CLAUDE.md).
- ✅ V4 gemeinsame Retry-Routine (`&shading_start_retry`)
- ✅ V7 gemeinsamer Manual-Tail; der Unknown-Zweig ist jetzt echter
  `default:` (schließt nebenbei den Silent-Drop-Randfall)
- ✅ V1 Force-Pause-Handler: 10 → 5 Zweige (Switch über `effective_state`)
- ✅ V3 `&drive_with_actions`-Anker, 36 von 37 Call-Sites umgestellt
- ✅ V2 Force-Enabled und Last-Wins parametrisiert. Die Recovery-Kaskade
  wurde bewusst NICHT aus `effective_state` abgeleitet: die Reihenfolge
  weicht absichtlich ab (base=cls gewinnt gegen gemerktes shd=1 —
  nachts nicht in die Beschattung hochfahren; Lockout-Return an
  Ventilation-Enable gebunden).
- ✅ V5 Handbuch unter `docs/handbook/` (17 Kapitel), `<details>`-Blöcke
  und die längsten Beschreibungen ausgelagert, Blueprint/README/FAQ
  verlinken darauf.

Ergebnis: 7.794 → ~6.830 Zeilen (−12 %), −~35 choose-Zweige. Offen /
bewusst nicht umgesetzt: Befund #5 (Restart-Verhalten der
Template-Trigger, HA-Einschränkung — nur dokumentiert), Befund #6
(Reset-default synchronisiert `bas` nicht — Verhaltensfrage), tiefere
FAQ-Handbuch-Verschmelzung (bestehende Deep-Links).
