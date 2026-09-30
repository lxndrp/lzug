# ADR-0036: PowerShell-Adapter für portable Werkzeuggrenzen

## Datum

2026-09-15.

## Status

Akzeptiert.

## Kontext

Task muss wenige portable Übergänge zwischen Standardwerkzeugen und den
komponenteneigenen Verträgen ausführen.
Shell- und Workflowblöcke vervielfachen dabei Quoting-, Exit-Code- und
Temporärdateifehler über Betriebssystemgrenzen.

## Entscheidung

PowerShell wird über `mise` gepinnt und für erforderliche lokale und
CI-Übergänge verwendet.
Die konkrete Version steht ausschließlich in `.mise.toml`.
Die Taskfile bleibt die öffentliche Einstiegsschnittstelle.
Zweckgebundene `scripts/*.ps1`-Adapter rufen Angular und die bestehende
Transportgenerierung auf; die Deploygrenze liegt beim zuständigen
`deployment/demo/deploy.ps1`-Adapter.
PowerShell besitzt keine Fach-, Persistenz-, Task-Graph- oder
Komponentenlogik.

`mise` verwaltet Versionen, Task ordnet Abläufe zu, PowerShell verbindet die
Werkzeuge, und Python, Angular, Docker, GoReleaser sowie Azure CLI bleiben
Eigentümer ihrer jeweiligen Verträge.
Native Exit-Codes, URL-/JSON-Grenzen und temporäres Staging werden am Adapter
fail-closed behandelt.
Die übergreifende Reihenfolge aus nativer Konfiguration, Standardmechanismen
und Zuordnung verbleibender Logik ist in
[ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md) festgelegt.

## Konsequenzen

Lokale Frontend-Builds und Transportgenerierung verwenden die passenden
Adapter; Container-Builds kopieren die bereits gebauten Frontend-Assets direkt
und installieren oder rufen dafür PowerShell nicht auf.
Der Demo-Deployadapter verwendet PowerShell in seinem eigens konfigurierten CI-
Schritt.
Die bestehenden Python- und Shell-Verträge für fachliche Prüfungen,
Container-Smokes und SBOMs bleiben getrennt und werden nicht in PowerShell
nachgebaut.
PowerShell ist weder eine Abhängigkeit der Frontend-Buildstages noch der
Runtimeimages.

## Abgrenzung

PowerShell ersetzt weder Task noch `mise`, `uv`, npm, Angular, Docker,
GoReleaser oder Azure CLI.
Ein gemeinsames PowerShell-Modul wird erst eingeführt, wenn nachweisbare
Wiederverwendung über mehrere Adapter entsteht.

## Referenzen

- [ADR-0003: Toolchain mit mise, uv und npm](0003-toolchain-mise-uv-npm.md)
- [ADR-0009: Toolchain und Entwicklungs-Tasks trennen](0009-toolchain-und-entwicklungs-tasks.md)
- [ADR-0021: GoReleaser für die Betreiber-CLI](0021-goreleaser-fuer-die-betreiber-cli.md)
