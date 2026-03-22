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

**Konkret:** `helper_json.win` (= `helper_state_window`) wird nur aktualisiert wenn der Contact-Handler das Cover tatsächlich bewegt. Wenn das Cover bei Fensteröffnung bereits an der Zielposition war, bleibt `win` im Helper auf `cls` — obwohl das Fenster physisch offen ist. Daher im `resident_arriving`-Handler immer `states(contact_window_opened)` verwenden, nicht `helper_state_window`.

### ⚠️ Invariante 4: `resident_leaving` — `allow_shade`/`allow_ventilate` gegen neue Status evaluieren

Im `resident_leaving`-Handler basiert `resident_flags.allow_shade` auf `state_resident` — und der liest aus `helper_json.res` (noch nicht aktualisiert → noch `1`). Dadurch liefert `allow_shade` = `not state_resident` = `false`, wenn `resident_allow_shading` nicht konfiguriert ist.

**Falsch:**
```yaml
- "{{ resident_flags.allow_shade }}"  # Liest alten Helper-Zustand!
```

**Richtig:**
```yaml
- "{{ new_resident_status == 0 or resident_flags.allow_shade }}"
# oder direkt: new_resident_status == 0 ist im leaving-Kontext immer true
```

Da im `leaving`-Kontext `new_resident_status` immer `0` ist, kann der Guard vereinfacht werden zu `new_resident_status == 0`.

### ⚠️ Invariante 5: `opened` hat immer Vorrang vor `tilted`

In **jedem** Branch/Handler, der sowohl `contact_window_opened` als auch `contact_window_tilted` behandelt, muss der `tilted`-Zweig explizit prüfen, dass `opened` **nicht** aktiv ist:

```yaml
# Tilted-Branch muss immer diese Bedingung enthalten:
- "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}"
```

Fehlende Priority-Checks zwischen opened/tilted führen dazu, dass bei gleichzeitig aktiven Sensoren der tilted-Branch feuert und nur auf Ventilationsposition (z.B. 50%) fährt statt auf die Open-Position (100%).

**Betrifft alle Handler:** `resident_leaving`, `resident_arriving`, `force_disabled`, `contact_sensor_changed`, Shading-Start/-End.

### ⚠️ Invariante 6: Lockout funktioniert unabhängig von `resident_allow_ventilation`

Der Lockout-Schutz (Fenster komplett offen → Cover auf Open-Position) ist eine **Sicherheitsfunktion** und darf nicht von `resident_flags.allow_ventilate` abhängen.

**Falsch:** Contact-Handler komplett mit `resident_flags.allow_ventilate` gaten → Lockout deaktiviert wenn `resident_allow_ventilation` nicht konfiguriert.

**Richtig:** `resident_flags.allow_ventilate` nur im tilted-Branch prüfen. Der opened-Branch (Lockout) muss immer laufen.

### ⚠️ Invariante 7: `man: 0` nur bei echten Cover-Drives setzen

Der `man`-Flag (manueller Override) darf nur auf `0` gesetzt werden, wenn das Automation das Cover tatsächlich auf eine definierte Position bewegt. In folgenden Situationen **nicht** `man: 0`:

- Pending-Timer (Shading Start/End Pending)
- Lockout-Blöcke ohne Drive (Cover bereits an Zielposition)
- Reine State-Änderungen ohne Bewegung
- Win-only Helper-Updates

**Falsch:** `man: 0` in `update_values` für jeden Block der `*helper_update` aufruft.
**Richtig:** `man: 0` nur in `update_values` für Blöcke, die auch `*cover_move_action` ausführen.

### ⚠️ Invariante 8: Timestamp-Invarianten

**ts.shd (Beschattungs-Timestamp):**
- `ts.shd` darf nur gesetzt werden, wenn `shd` sich tatsächlich ändert (guard in `helper_update`: nur wenn `new_shd != current.shd`)
- Im SHADED-Branch des `resident_leaving`-Handlers: `shd` war schon `1` (Precondition) → `ts.shd` **nicht** auf `now` setzen, ursprünglichen Zeitstempel erhalten

**ts.shs / ts.she (Shading-Pending-Timestamps):**
- Diese dürfen nicht resettet werden in win-only Helper-Updates (wenn nur `win` aktualisiert wird, ohne dass ein Drive stattfand)

---

## Bekannte Bug-Muster (mit Ursache und Fix)

### Bug-Muster A: Branch-Selektion durch Positions-Check blockiert

**Symptom:** Wenn Cover bereits an Zielposition X, wird beim nächsten Trigger fälschlicherweise ein niedrigerprioritärer Branch ausgeführt (z.B. Shading statt Lockout).

**Ursache:** `effective_state != 'X' or not in_X_position` in Branch-Conditions → bei Position=X und effective_state=X ist die Bedingung `FALSE`, Branch wird übersprungen.

**Betroffene Stellen (zuletzt gefunden):**
- Zeile ~5729: `resident_leaving` → LOCKOUT-Branch (behoben)
- Zeile ~5758: `resident_leaving` → VENT-Branch (behoben)
- `resident_arriving` mit `resident_allow_ventilation` aktiviert (behoben)

**Fix:** Positions-Check in den `if:`-Guard verschieben:
```yaml
if: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
```

### Bug-Muster B: `resident_flags.allow_shade/allow_ventilate` im `resident_leaving`-Handler

**Symptom:** Nach Resident-Abwesenheit fährt Cover auf Open-Position statt auf Shading- oder Ventilationsposition.

**Ursache:** `resident_flags.allow_shade` basiert auf `state_resident` = `helper_json.res` = noch `1` (alter Wert). Daher `allow_shade` = `false` wenn `resident_allow_shading` nicht konfiguriert → Branch übersprungen.

**Fix:** Im `resident_leaving`-Handler `new_resident_status == 0` statt `resident_flags.allow_shade` verwenden:
```yaml
- "{{ new_resident_status == 0 or 'resident_allow_shading' in resident_config }}"
```

### Bug-Muster C: Lockout durch `resident_allow_ventilation`-Gate blockiert

**Symptom:** Wenn `resident_allow_ventilation` nicht konfiguriert ist, funktioniert der Lockout-Schutz nicht mehr.

**Ursache:** `resident_flags.allow_ventilate` als Top-Level-Bedingung im Contact-Handler gatet den gesamten Ventilations-Handler inklusive Lockout.

**Fix:** `resident_flags.allow_ventilate` nur im tilted-Sub-Branch prüfen, nicht als globale Condition des Contact-Handlers.

### Bug-Muster D: Fehlender `not contact_window_opened`-Check im tilted-Branch

**Symptom:** Bei gleichzeitig aktiven `contact_window_opened` und `contact_window_tilted` fährt Cover auf Ventilationsposition (50%) statt Open-Position (100%).

**Ursache:** Der tilted-Branch prüft nicht, ob opened ebenfalls aktiv ist. Da opened- und tilted-Branch die gleiche Priorität zu haben scheinen, kann tilted zuerst matchen.

**Fix:** In **jedem** tilted-Branch hinzufügen:
```yaml
- "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}"
```

### Bug-Muster E: `man: 0` in Nicht-Bewegungs-Blöcken

**Symptom:** Manueller Override wird unerwartet zurückgesetzt, obwohl kein Cover-Drive stattfand.

**Ursache:** `man: 0` in `update_values` für jeden Block mit `*helper_update`, auch wenn kein Drive erfolgt.

**Fix:** `man: 0` entfernen aus: Pending-Timern, Lockout-only-Blöcken, reine State-Updates.

### Bug-Muster F: Phantom-Timestamp-Updates

**Symptom:** `ts.shd` zeigt falschen Zeitstempel; Shading-Pending-State wird unerwartet zurückgesetzt.

**Ursache A:** `ts.shd: "now"` wird in Sequences gesetzt, die `shd` gar nicht von 0→1 ändern.
**Ursache B:** `ts.shs/ts.she` werden in win-only Helper-Updates resettet.

**Fix:** Guard in `helper_update` — `ts.shd` nur anwenden wenn `new_shd != current.shd`. `ts.shs/ts.she` nicht in win-only Updates resetten.

### Bug-Muster G: `helper_state_window` statt Realtime-Sensor im `resident_arriving`-Handler

**Symptom:** Wenn Cover bereits an Open-Position war als Fenster geöffnet wurde, erkennt `resident_arriving` den Lockout-Zustand nicht → Cover schließt fälschlicherweise.

**Ursache:** `helper_json.win` wird nur aktualisiert wenn ein Drive erfolgt. War Cover bereits offen, bleibt `win = 'cls'` im Helper.

**Fix:** Im `resident_arriving`-Handler immer Realtime-Sensoren prüfen:
```yaml
# Falsch: helper_state_window != 'opn'
# Richtig:
- "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
```

---

## Unit-Tests ausführen

```bash
pip install pytest jinja2 pyyaml
pytest tests/ -v
```

Tests prüfen die Prioritätskaskade für kritische Szenarien ohne echtes Home Assistant.
