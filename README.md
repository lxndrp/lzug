# lzug

`lzug` ist eine Web-App zur Unterstützung eines IHK-Prüfungsausschusses bei der Organisation halbjährlicher Fachinformatiker-Prüfungen.

Der aktuelle Fokus liegt auf der Prüfungsrunde:

- Verwaltung von Prüflingen
- Import von Prüflingsdaten
- Pflege von Ausschussmitgliedern und Prüfungsorten
- Terminfindung mit Verfügbarkeiten
- automatisierter Planungsvorschlag
- MEP- und Prüfungsversuchslogik
- Vorbereitung eines persistenten Server-Datenmodells

## Projektstruktur

```text
lzug/
├── db/
│   ├── schema.sql
│   └── seed_demo.sql
├── docs/
│   ├── datenmodell.md
│   ├── relationales-schema.md
│   └── backend-prototyp.md
├── server/
│   ├── app.py
│   ├── database.py
│   ├── models.py
│   ├── repositories.py
│   └── store.py
└── prototypes/
    └── pruefungsrunde-prototyp/
        ├── index.html
        ├── app.js
        ├── styles.css
        └── README.md
```

## Aktueller Stand

Der klickbare Prototyp ist eine statische Web-App ohne Build-Schritt. Er kann lokal direkt im Browser geöffnet werden:

```text
prototypes/pruefungsrunde-prototyp/index.html
```

Das fachliche Datenmodell befindet sich in:

```text
docs/datenmodell.md
```

Das relationale Basisschema befindet sich in:

```text
db/schema.sql
```

Die technische Einordnung des ersten Backends ist dokumentiert in:

```text
docs/backend-prototyp.md
```

Ein erster persistenter Backend-Prototyp nutzt SQLite über SQLAlchemy. Die Abhängigkeiten sind in `pyproject.toml` beschrieben:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Der Server startet danach mit:

```bash
.venv/bin/python -m server.app --init --seed --reset
```

Danach stehen JSON-Endpunkte unter `http://127.0.0.1:8000/api/` bereit, z. B.:

```text
/api/health
/api/round-summary?round_id=1
/api/candidates
/api/candidates/1
/api/members
/api/locations
/api/planning-settings?round_id=1
/api/candidate-exam-days?round_id=1
/api/member-availabilities?round_id=1
```

Für die Kernressourcen `committees`, `members`, `locations`, `exam-rounds` und `candidates` sind die CRUD-Muster `GET`, `POST`, `PATCH` und `DELETE` vorbereitet. Planungsparameter und Verfügbarkeiten sind ebenfalls schreibbar; `POST /api/planning-settings` und `POST /api/member-availabilities` aktualisieren vorhandene Einträge für dieselbe Prüfungsrunde bzw. dieselbe Mitglied/Tag-Kombination.

## Tests

Der Test-Harness nutzt `unittest` und die in `pyproject.toml` beschriebenen Projektabhängigkeiten. Er deckt die aktuellen Applikationsteile ab:

- Datenbankschema, Seed-Daten und Kern-Constraints
- Repository-Funktionen und Rundenzusammenfassung
- JSON-API über den echten HTTP-Handler ohne lokalen Port
- statischen Prototyp mit Asset-, Navigations- und JavaScript-Syntaxprüfung

Alle Tests laufen mit:

```bash
.venv/bin/python -m unittest
```

Coverage ist als Dev-Extra konfiguriert:

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m coverage run -m unittest
.venv/bin/python -m coverage report
.venv/bin/python -m coverage xml
```

In VS Code stehen dafuer die Tasks `Tests mit Coverage`, `Coverage XML erzeugen` und `Coverage HTML erzeugen` bereit. Die empfohlene Erweiterung Coverage Gutters nutzt `coverage.xml` direkt im Editor.

Wenn Node.js installiert ist, prüft der Harness zusätzlich `app.js` mit `node --check`; ohne Node wird nur dieser optionale Syntaxcheck übersprungen.

## Nächster geplanter Schritt

Der nächste sinnvolle Schritt ist, Planungsvorschläge und die zugehörigen fachlichen Service-Regeln auszubauen. Die Regeln aus `docs/relationales-schema.md` sollten dabei in Service-Funktionen validiert werden.
