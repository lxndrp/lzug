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
├── docs/
│   └── datenmodell.md
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

## Nächster geplanter Schritt

Aus dem fachlichen Datenmodell soll ein relationales Datenbankschema abgeleitet werden. Dieses Schema dient danach als Grundlage für eine Server-App, die Daten dauerhaft speichert.
