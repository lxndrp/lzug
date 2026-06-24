# lzug – relationales Schema

Stand: 24.06.2026

Dieses Dokument beschreibt den ersten relationalen Schemaentwurf für die Server-App. Die ausführbare SQL-Datei liegt unter:

```text
db/schema.sql
```

## Entwurfsentscheidung

Das Schema ist bewusst als robuste Zwischenform angelegt:

- Primärschlüssel zunächst als `INTEGER PRIMARY KEY`, damit SQLite ohne Zusatzaufwand funktioniert.
- Fachliche Enums werden als `TEXT` mit `CHECK`-Constraints modelliert.
- Zeitstempel werden als `TEXT` mit `CURRENT_TIMESTAMP` abgelegt. Für PostgreSQL kann später auf `TIMESTAMPTZ` umgestellt werden.
- Booleans werden als `INTEGER` mit `CHECK (wert IN (0, 1))` modelliert. Für PostgreSQL kann später `BOOLEAN` verwendet werden.
- Komplexe fachliche Regeln, die mehrere Zeilen betreffen, werden nicht vollständig per Datenbank-Constraint erzwungen, sondern in der Anwendungslogik validiert.

Das klingt ein wenig handwerklich, ist aber für die erste Server-App angenehm: wenig Magie, gut migrierbar, schnell testbar.

## Enthaltene Tabellen

### Stammdaten

- `committee`
- `committee_member`
- `user_account`
- `location`
- `candidate`

### Prüfungsdurchgang und Planung

- `exam_round`
- `round_candidate`
- `planning_settings`
- `candidate_exam_day`
- `member_availability`
- `exam_day`
- `exam_slot`
- `exam_day_assignment`

### Ausfall, Kommunikation und Kalender

- `absence_report`
- `replacement_response`
- `notification`
- `calendar_event`

## Wichtige Constraints

Das Schema erzwingt direkt in der Datenbank unter anderem:

- eindeutige IHK-Prüfungsnummer je Prüfling
- eindeutige E-Mail-Adresse je Ausschussmitglied innerhalb eines Ausschusses
- maximal einen Vorsitzenden je Ausschuss
- maximal einen stellvertretenden Vorsitzenden je Ausschuss
- pro Prüfungsdurchgang einen Prüfling nur einmal
- pro Prüfungsdurchgang genau einen Satz Planungsparameter
- pro Prüfungstag eindeutige Slot-Reihenfolge
- pro Prüfling und Durchgang höchstens einen regulären Slot und höchstens einen MEP-Slot
- `attempt_number >= 1`
- `exams_per_day >= 1`
- `max_exam_days_per_week` zwischen 1 und 5
- Fallback-Besetzungen benötigen einen Fallback-Status
- 2FA darf nur aktiviert sein, wenn Passkeys aktiviert sind

## Fachliche Regeln, die in der Anwendung validiert werden

Einige Regeln betreffen mehrere Datensätze und sollten in der Serverlogik validiert werden:

### Besetzung eines Prüfungstags

Für jeden relevanten Tagesabschnitt:

- mindestens drei reguläre Prüfer
- Arbeitgeberseite vertreten
- Arbeitnehmerseite vertreten
- Schulseite vertreten
- zusätzlicher Fallback-Prüfer
- Fallback ist nicht zugleich regulärer Prüfer desselben Abschnitts

### MEP-Regeln

Für jeden Prüfungstag:

- MEP-Slots liegen am Ende des Tages
- ein Tag besteht nie ausschließlich aus MEP-Slots
- ein MEP-Slot existiert nur für Prüflinge mit `round_candidate.requires_mep = 1`

### Slot-Regeln

- Jeder `round_candidate` benötigt genau einen regulären Slot.
- Wenn `requires_mep = 1`, benötigt der `round_candidate` zusätzlich genau einen MEP-Slot.
- Ein Slot dauert fachlich immer 60 Minuten.
- Bei aktivierter Mittagspause darf kein Slot in die Pause 12:30–13:30 fallen.

### Rechte

- Vorsitzender und stellvertretender Vorsitzender dürfen Stammdaten und Planungsdaten bearbeiten.
- Nur der Vorsitzende darf `planning_settings.max_exam_days_per_week` ändern.
- Normale Mitglieder dürfen ihre Verfügbarkeiten melden und Ausfälle melden.

## PostgreSQL-Migration später

Wenn wir nach dem ersten Server-Prototyp auf PostgreSQL festziehen, wären diese Änderungen sinnvoll:

- `INTEGER PRIMARY KEY` durch `UUID PRIMARY KEY DEFAULT gen_random_uuid()` ersetzen
- `TEXT`-Zeitstempel durch `TIMESTAMPTZ` ersetzen
- Boolean-Spalten auf `BOOLEAN` umstellen
- `TEXT`+`CHECK`-Enums optional durch echte PostgreSQL-Enums oder Lookup-Tabellen ersetzen
- Trigger für `updated_at` ergänzen
- zusätzliche Exclusion Constraints für überlappende Slots prüfen

## Nächster Schritt

Als nächstes sollte das Schema gegen SQLite oder PostgreSQL geladen werden. Danach können wir Seed-Daten aus dem klickbaren Prototyp übertragen und erste Repository-/Service-Funktionen für die Server-App skizzieren.
