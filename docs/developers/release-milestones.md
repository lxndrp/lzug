# Release- und Milestone-Migrationsregister

Stand: 11.08.2026

Dieses Register dokumentiert die kontrollierte SemVer-Migration. Es
ist die nachvollziehbare Begründung für jedes am Stichtag offene Issue. Die
verbindliche Semantik steht in
[ADR-0018](decisions/0018-semver-release-und-milestones.md).

## Beschlossene Releasefolge

Die Fälligkeiten sind Prognosen aus 12 bis 16 Stunden persönlicher Kapazität je
14-Tage-Iteration. Ein Datum ist kein Freigabeautomatismus.

| Milestone     | Prognose      | Offene Issues am Stichtag                | Begründung der Zielmenge                                                                                         |
| ------------- | ------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `v0.1.0`      | 09.10.2026    | #304, #305, #306, #307, #308             | gemeinsame Qualitäts-, Versions- und kandidatenbasierte Release-Infrastruktur                                    |
| `v0.2.0`      | 23.10.2026    | #25, #313, #314, #315                    | kontrollierte Bearbeitung eines Planungsvorschlags einschließlich Aggregat, API und barrierefreiem Editor        |
| `v0.3.0`      | 06.11.2026    | #28, #29, #30                            | zusammenhängender Ausfall-, Benachrichtigungs- und Kalenderprozess                                               |
| `v0.4.0`      | 20.11.2026    | #20, #34, #35, #36                       | mündlichen Prüfungstag durchführen, Ergebnisse modellieren und den Tag abschließen                               |
| `v0.5.0`      | 18.12.2026    | #19, #84, #89, #311                      | bestätigten Plan kontrolliert ändern sowie Halbjahr abschließen und historisieren                                |
| `v0.6.0`      | 26.02.2027    | #120, #130, #150, #270, #271, #272, #273 | selbst betreibbarer Stand mit Backup, Restore, Upgrade, Rollback und reproduzierbarer Betreiber-CLI              |
| `v1.0.0-rc.1` | 26.03.2027    | #49, #108, #168, #175, #267              | integrierter, beobachtbarer und unter realen Bedingungen abnehmbarer Winterpilot                                 |
| `v1.0.0`      | 07.05.2027    | #318                                     | ausgewertete Pilotnutzung, geschlossene blockierende Befunde und ausdrückliche stabile Freigabe                  |
| `v1.1.0`      | bewusst offen | #165                                     | schriftliche Prüfungen als eigenständig nutzbarer post-1.0-Fachprozess; Termin erst nach fachlicher Verfeinerung |

## Bewusst ohne Release-Milestone

Diese Issues bleiben im GitHub Project beziehungsweise in ihrer
Parent-/Child-Struktur planbar, versprechen aber keine konkrete
Produktversion.

| Gruppe                                     | Issues                             | Begründung                                                                                                                  |
| ------------------------------------------ | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| format- oder fachlich ungeklärt            | #21, #22, #164, #226               | reale Eingabeformate oder fachlicher Umfang sind noch nicht ausreichend geklärt                                             |
| releaseübergreifende Epics                 | #26, #46, #113                     | Children betreffen unterschiedliche oder noch unbestimmte Releases; die tatsächlichen Release-Items sind einzeln zugeordnet |
| öffentliche Demo                           | #124, #125, #126, #127, #128, #129 | Deployment und Betrieb der flüchtigen Demo sind kein Bestandteil der Produktversionsidentität                               |
| nachrangige oder entkoppelte Themen        | #132, #133, #134, #206, #268, #309 | noch nicht terminierte Architektur-, Rechts- oder Produktentscheidungen ohne belastbaren Releasebezug                       |
| internes Tooling und Dokumentationsbetrieb | #154, #229, #293                   | Agent-, Wiki- und Entwicklungsumgebung ändern keinen auszuliefernden Produktumfang                                          |
| technische Roll-ups                        | #301, #302                         | die releasewirksamen Children sind einzeln zugeordnet; der Parent wird nicht doppelt gezählt                                |

## Historische Milestones

| Bisheriger Milestone                     | Ergebnis                                                                      | Historie                                                                                                                               |
| ---------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Fachlich vollständiger Prototyp          | in `v0.1.0` umbenannt und offene Zielmenge auf `v0.1.0` bis `v0.6.0` verteilt | geschlossene Issue-Verknüpfungen bleiben als Planungshistorie erhalten                                                                 |
| Version 1 – Wintererprobung              | in `v1.0.0` umbenannt und Pilotumfang nach `v1.0.0-rc.1` verschoben           | geschlossene Issue-Verknüpfungen bleiben als Planungshistorie erhalten                                                                 |
| Veröffentlichungs- und Betriebsfähigkeit | als historischer Themencontainer geschlossen                                  | geschlossene Issues und externe Verweise bleiben erhalten; offene Issues wechseln nach `v0.1.0` oder verlieren begründet die Zuordnung |
| Öffentlicher Quellcode-Prototyp          | unverändert geschlossen                                                       | dokumentiert ausschließlich die öffentliche Repository-Freigabe                                                                        |

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
