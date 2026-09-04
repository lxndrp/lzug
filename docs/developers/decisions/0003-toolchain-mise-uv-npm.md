# ADR-0003: Toolchain mit mise, uv und npm

## Datum

2026-07-26.

## Status

Akzeptiert.
Rückwirkend dokumentiert.

## Kontext

Das Projekt benötigt reproduzierbare Runtime-Versionen und Lockfile-basierte Abhängigkeiten.

## Entscheidung

`mise` verwaltet Python 3.14.6, Node.js 26.5.0, Go 1.26.5, uv, Task, das für CycloneDX-SBOMs gepinnte Syft und GoReleaser für die sechs nativen Betreiber-CLI-Archive.
`uv` erzeugt die Python-Umgebung und löst Abhängigkeiten gegen `uv.lock` auf.
Task orchestriert die projektweiten Entwicklungsabläufe.
Das Frontend verwendet npm mit `frontend/package-lock.json`; pnpm wird nicht verwendet.

## Konsequenzen

Die lokale Einrichtung erfolgt über `mise install` und `task setup`. CI verwendet dieselben Versionen und Lockfiles. Versionspins in `.mise.toml`, `.python-version` und `frontend/.node-version` werden bewusst manuell bewertet. Die konkrete Bedienung steht in [Entwicklung](../development.md) und in [ADR-0009](0009-toolchain-und-entwicklungs-tasks.md).
