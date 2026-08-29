# ADR-0005: Taiga UI für die Oberfläche

## Datum

2026-07-26.

## Status

Akzeptiert.
Rückwirkend dokumentiert.

## Kontext

Eine begrenzte Taiga-UI-Erprobung bestätigte die technische und gestalterische Richtung für eine inkrementelle Migration.

## Entscheidung

Backend, API-Verträge, Routen und fachliche Abläufe blieben dabei unverändert.
Taiga UI deckt die produktiven Oberflächenkomponenten ab.

## Konsequenzen

Taiga UI ist die gewählte Komponentenbibliothek.
Native oder anwendungseigene Elemente bleiben nur dort bestehen, wo keine semantisch gleichwertige Komponente verfügbar ist.
Die Git-Historie bewahrt frühere Migrationsentscheidungen.
