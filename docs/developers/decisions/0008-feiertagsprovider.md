# ADR-0008: Kuratierte Feiertagsdaten über einen Provider

## Datum

2026-07-26.

## Status

Akzeptiert.
Rückwirkend dokumentiert.

## Kontext

Die Planung möglicher Prüfungstage muss bundesweite und landesweit geltende gesetzliche Feiertage berücksichtigen, ohne die Planungslogik an eine konkrete Datenquelle zu koppeln.

## Entscheidung

Dafür verwendet das Backend die kuratierte Python-Bibliothek `holidays` hinter
der eigenen `HolidayProvider`-Schnittstelle in
`backend/src/backend/holiday_provider.py`.

## Konsequenzen

Planungslogik arbeitet gegen den Provider und kann die konkrete Datenquelle später austauschen.
Gemeindespezifische Sonderregeln werden bei einer reinen Bundeslandauswahl nicht abgeleitet.
Änderungen an diesem Verhalten verlangen Tests für die betroffenen Berechnungen.
