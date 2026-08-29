# ADR-0005: Taiga UI für die Oberfläche

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Eine begrenzte Taiga-UI-Erprobung bestätigte die technische und gestalterische Richtung für eine inkrementelle Migration.
Backend, API-Verträge, Routen und fachliche Abläufe blieben dabei unverändert.
Taiga UI deckt die produktiven Oberflächenkomponenten ab.

## Konsequenzen

Taiga UI ist die gewählte Komponentenbibliothek.
Native oder anwendungseigene Elemente bleiben nur dort bestehen, wo keine semantisch gleichwertige Komponente verfügbar ist.
Die Git-Historie bewahrt frühere Migrationsentscheidungen.
