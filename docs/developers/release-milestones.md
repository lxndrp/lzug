# Release- und Milestone-Migrationsregister

Stand: 11.08.2026

Dieses Register dokumentiert die kontrollierte SemVer-Migration. Es
ist die nachvollziehbare Begründung für jedes am Stichtag offene Issue. Die
verbindliche Semantik steht in
[ADR-0018](decisions/0018-semver-release-und-milestones.md).

## `v0.1.0`

`v0.1.0` ist das erste konkrete Releaseziel: ein fachlich vollständiger,
self-hostbarer Stand mit dem dafür notwendigen Qualitäts-, Betriebs- und
Veröffentlichungsvertrag.

| Gruppe | Issues | Begründung |
| --- | --- | --- |
| fachlich vollständiger Prototyp | #20, #25, #28, #29, #34, #35, #36, #84, #89, #313, #314, #315 | bestehende Zielmenge des umbenannten Milestones |
| Self-Hosting und Betrieb | #120, #130, #132, #270, #271, #272, #273 | für eine betreibbare erste Veröffentlichung erforderliche Sicherung, Dokumentation und Operator-Pfade |
| Qualität und Releasevertrag | #301, #302, #304, #305, #306, #307, #308 | notwendige Qualitäts-, Versions- und Freigabegrundlage des ersten Releases |

## `v1.0.0`

`v1.0.0` ist die stabilisierte Version für die Wintererprobung am 06.11.2026.

| Gruppe | Issues | Begründung |
| --- | --- | --- |
| fachlicher und technischer Abschluss | #19, #30, #46, #49, #108, #168, #175, #267, #311 | bestehender Umfang der Wintererprobung; release-unabhängiges Agent-Tooling wird herausgenommen |

## Bewusst ohne Release-Milestone

Diese Issues bleiben im GitHub Project beziehungsweise in ihrer
Parent-/Child-Struktur planbar, versprechen aber keine konkrete
Produktversion.

| Gruppe | Issues | Begründung |
| --- | --- | --- |
| format- oder fachlich ungeklärt | #21, #22, #164, #165, #226 | reale Eingabeformate oder fachlicher Umfang sind noch nicht ausreichend geklärt |
| releaseübergreifende Epics | #26, #113, #150 | Children betreffen unterschiedliche oder noch unbestimmte Releases; die tatsächlichen Release-Items sind einzeln zugeordnet |
| öffentliche Demo | #124, #125, #126, #127, #128, #129 | Deployment und Betrieb der flüchtigen Demo sind kein Bestandteil der Produktversionsidentität |
| nachrangige Konzepte | #133, #134, #206, #268, #309 | noch nicht terminierte Architektur- oder Produktentscheidungen ohne belastbaren Releasebezug |
| internes Tooling und Dokumentationsbetrieb | #154, #229, #293 | Agent-, Wiki- und Entwicklungsumgebung ändern keinen auszuliefernden Produktumfang |

## Historische Milestones

| Bisheriger Milestone | Ergebnis | Historie |
| --- | --- | --- |
| Fachlich vollständiger Prototyp | in `v0.1.0` umbenannt | Fälligkeit und sämtliche Issue-Verknüpfungen bleiben erhalten |
| Version 1 – Wintererprobung | in `v1.0.0` umbenannt | Fälligkeit und sämtliche Issue-Verknüpfungen bleiben erhalten |
| Veröffentlichungs- und Betriebsfähigkeit | als historischer Themencontainer geschlossen | geschlossene Issues und externe Verweise bleiben erhalten; offene Issues wechseln nach `v0.1.0` oder verlieren begründet die Zuordnung |
| Öffentlicher Quellcode-Prototyp | unverändert geschlossen | dokumentiert ausschließlich die öffentliche Repository-Freigabe |

## Pflege

- Neue Issues erhalten nur dann einen Release-Milestone, wenn ihr tatsächlicher
  Lieferumfang für diese Version beschlossen ist.
- Milestone, Project-Iteration und Project-Zieltermin werden nicht automatisch
  voneinander abgeleitet.
- Ein Planungsreview prüft offene Issues auf genau einen SemVer-Milestone oder
  eine weiterhin tragfähige Entscheidung ohne Releasezuordnung.
- Eine Änderung dieser Zuordnung wird im betroffenen Issue begründet; dieses
  Register bleibt der Migrationsnachweis für den Stichtag und wird nicht als
  zweite operative Planungsdatenbank fortgeschrieben.
