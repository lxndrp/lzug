# ADR-0003: Toolchain mit mise, uv und npm

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Das Projekt benötigt reproduzierbare Runtime-Versionen und Lockfile-basierte Abhängigkeiten für Python und das Angular-Frontend. `mise` verwaltet Python 3.14.6, Node.js 26.5.0, uv und Task. `uv` erzeugt die Python-Umgebung und löst Abhängigkeiten gegen `uv.lock` auf. Task orchestriert die projektweiten Entwicklungsabläufe. Das Frontend verwendet npm mit `frontend/package-lock.json`; pnpm wird nicht verwendet.

## Konsequenzen

Die lokale Einrichtung erfolgt über `mise install` und `task setup`. CI verwendet dieselben Versionen und Lockfiles. Versionspins in `.mise.toml`, `.python-version` und `.node-version` werden bewusst manuell bewertet. Die konkrete Bedienung steht in [Entwickler-Setup](../setup.md) und [ADR-0009](0009-toolchain-und-entwicklungs-tasks.md). Die lokale Laufzeit ist im GitHub Wiki beschrieben.
