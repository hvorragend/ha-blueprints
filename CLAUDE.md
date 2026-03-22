# CLAUDE.md — Cover Control Automation (CCA) Blueprint

## Überblick

`blueprints/automation/cover_control_automation.yaml` ist ein Home Assistant Automatisierungs-Blueprint (Jinja2 + YAML). Das Blueprint steuert Rollläden/Jalousien basierend auf Zeit, Sonne, Fenster-Kontaktsensoren und Anwesenheit.

---

## Helper-JSON-Schema (v6)

Der Zustand wird als JSON-String in einem `input_text`-Helper persistiert:

```json
{"bas":"opn","shd":1,"win":"opn","frc":"non","res":1,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"shs":0,"she":0,"win":0,"man":0,"res":0},
 "v":6,"t":0}
```

| Feld | Werte | Bedeutung |
|------|-------|-----------|
| `bas` | `opn`/`cls` | Base-Zustand (Zeit-basiert: offen / geschlossen) |
| `shd` | `1`/`0` | Beschattung aktiv |
| `win` | `cls`/`tlt`/`opn` | Fensterzustand (geschlossen / gekippt / offen) |
| `frc` | `non`/`opn`/`cls`/`shd`/`vnt` | Aktive Force-Funktion |
| `res` | `1`/`0` | Bewohner anwesend |
| `man` | `1`/`0` | Manueller Override aktiv |
| `ts.*` | Unix-Timestamp | Zeitstempel der letzten Änderung je Feld |

---

## Prioritätskaskade (`effective_state`)

```
1. FORCE    → frc != "non"          → Force-Position
2. LOCKOUT  → win == "opn"          → Open-Position (Einschlusschutz)
3. VENT     → win == "tlt"          → Ventilationsposition
4. PRIVACY  → resident && closing   → Schließposition
5. SHADING  → shd == 1 && allow     → Beschattungsposition
6. BASE     → bas                   → Basisposition (opn/cls)
```

Die Variable `effective_state` gibt den aktuell gültigen Zustand aus dieser Kaskade zurück (`lock`, `vnt`, `cls`, `shd`, `opn`).

---

## Architekturinvarianten — IMMER BEACHTEN

### ⚠️ Invariante 1: Positions-Check NIEMALS in Branch-Conditions

**Falsch:**
```yaml
- conditions:
    - "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
    - "{{ effective_state != 'lock' or not in_open_position }}"  # ← HIER NICHT!
  sequence:
    - if: "{{ force_allows_ventilate }}"
      then: ...drive...
```

**Richtig:**
```yaml
- conditions:
    - "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
    # Kein Positions-Check hier!
  sequence:
    - if: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
      then: ...drive...
    - *helper_update  # Helper wird IMMER aktualisiert
```

**Warum:** Wenn der Positions-Check in den Branch-Conditions steht, wird der Branch nicht gewählt wenn das Cover bereits an der Zielposition ist. Dadurch fällt die Logik auf den nächsten Branch durch (z.B. Shading), was die Prioritätskaskade bricht.

**Regel:** Jeder Branch, der per Priorität Vorrang hat, muss **immer konsumiert** werden (auch wenn kein Drive nötig ist). Der Helper-Update soll immer stattfinden.

### ⚠️ Invariante 2: Helper immer aktualisieren

`*helper_update` muss am Ende **jedes** Branch-Sequences stehen — auch wenn kein Cover-Drive stattfindet. Nur so wird der `res`-Status (und andere Felder) korrekt persistiert.

### ⚠️ Invariante 3: Realtime-Sensor vs. Helper-Zustand

- `state_resident` / Sensor-Checks (`states(contact_window_opened)`) → **Realtime** (aktueller Sensor-Wert)
- `helper_state_window` / `helper_json.win` → **Helper** (zuletzt persistierter Zustand)

Im `resident_arriving`/`resident_leaving`-Handler: immer Realtime-Sensoren prüfen, da der Helper noch den alten Zustand hat.

---

## Bekannte Bug-Muster

### Bug-Muster A: Branch-Selektion durch Positions-Check blockiert

**Symptom:** Wenn Cover bereits an Zielposition X, wird beim nächsten Trigger fälschlicherweise ein niedrigerprioritärer Branch ausgeführt (z.B. Shading statt Lockout).

**Ursache:** `effective_state != 'X' or not in_X_position` in Branch-Conditions → bei Position=X und effective_state=X ist die Bedingung `FALSE`, Branch wird übersprungen.

**Betroffene Stellen (zuletzt gefunden):**
- Zeile ~5729: `resident_leaving` → LOCKOUT-Branch: `effective_state != 'lock' or not in_open_position` → **behoben**
- Zeile ~5758: `resident_leaving` → VENT-Branch: `effective_state != 'vnt' or not in_ventilate_position` → **behoben**

**Fix:** Positions-Check in den `if:`-Guard verschieben:
```yaml
if: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
```

### Bug-Muster B: `allow_ventilate` / `allow_shade` fehlt in Branch-Conditions

**Symptom:** Cover fährt auf Ventilations- oder Beschattungsposition obwohl Resident anwesend ist und die Option deaktiviert ist.

**Prüfung:** Alle Ventilations- und Shading-Branches müssen `resident_flags.allow_ventilate` bzw. `resident_flags.allow_shade` in ihren Conditions haben (außer wenn Fenster-Lockout Vorrang hat).

### Bug-Muster C: Race Condition bei gleichzeitiger Sensor-Änderung

**Symptom:** Zwei Sensoren ändern sich quasi-gleichzeitig (z.B. Fensterkontakt + Resident). Der zweite Trigger sieht noch den alten Helper-Zustand.

**Lösung:** `contact_delay_trigger`-Option nutzen. Immer Realtime-Sensoren prüfen, nicht `helper_json.*`.

---

## Unit-Tests ausführen

```bash
pip install pytest jinja2 pyyaml
pytest tests/ -v
```

Tests prüfen die Prioritätskaskade für kritische Szenarien ohne echtes Home Assistant.
