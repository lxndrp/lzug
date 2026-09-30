# ADR-0003: Toolchain mit mise, uv und npm

## Datum

2026-07-26.

## Status

Akzeptierte Grundentscheidung.
Rückwirkend dokumentiert; die aktuelle gemeinsame Zuständigkeitsregel steht
in ADR-0039.

## Kontext

Das Projekt benötigt reproduzierbare Runtime-Versionen und Lockfile-basierte Abhängigkeiten.

## Entscheidung

Die ursprüngliche Toolchain-Wahl legt `mise` für die Versionen ausführbarer
Werkzeuge und `uv` beziehungsweise npm für ihre jeweiligen Abhängigkeiten fest.
Die aktuelle gemeinsame Zuständigkeits- und Vorrangregel steht in
[ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md); konkrete Pins liegen
in `.mise.toml` und den nativen Manifesten und Lockfiles.
`Task` besitzt den öffentlichen Ablaufgraph, während komponenteneigene Tasks
bei ihren Komponenten liegen.
Das Frontend verwendet npm mit `frontend/package-lock.json`; pnpm wird nicht verwendet.

## Konsequenzen

Abhängigkeiten und ausführbare Werkzeuge bleiben an ihre jeweiligen nativen
Manifest-, Lockfile- und Versionsquellen gebunden.
Aktuelle Pins stehen in der nativen Konfiguration; Einrichtung und Bedienung
stehen in [Entwicklung](../development.md).
Die ursprüngliche Wahl wird durch die übergreifende aktuelle Zuständigkeits-
und Vorrangregel in [ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md)
präzisiert.
