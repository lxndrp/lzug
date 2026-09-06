# Für Entwickler

Dieses Handbuch ordnet den aktuellen technischen Stand der jeweils gebauten Repository-Revision.
Für Beiträge und lokale Entwicklung bleibt
[`CONTRIBUTING.md`](https://github.com/lxndrp/lzug/blob/master/CONTRIBUTING.md)
der verbindliche Einstieg.
Fachliche, Nutzungs- und Betreiberanleitungen liegen im Repository unter
[`docs/handbook/`](../handbook/Home.md) und den zielgruppenorientierten
[Portal-Einstiegen](../portal/produkt.md).

## Fünf Kernbereiche

- [Fachmodell und Verträge](data-and-contracts.md) erklärt Aggregate,
  Invarianten, Persistenz, Migrationen, HTTP/OpenAPI und die erzeugten
  Referenzen, ohne ausführbare Verträge als manuelle Liste zu duplizieren.
- [Architektur und Entscheidungen](architecture.md) zeigt Systemkontext,
  Container, Komponenten, Deployment, einen kritischen Ablauf, die
  Architekturprinzipien sowie Sicherheits-, Autorisierungs- und
  Observability-Grenzen.
- [Komponenten](components.md) ordnet Verantwortungen und erlaubte
  Abhängigkeiten von Backend, Frontend, Betreiber-CLI, OCI-Runtime und
  Demo-Infrastruktur.
- [Delivery und Veröffentlichung](delivery.md) verbindet Pull-Request-Gates,
  vollständige Qualität, Release, SBOM, Demo-Promotion sowie Site-Publikation.
- [Entwicklung](development.md) bündelt lokale Toolchain, Tasks, Testauswahl,
  Dependencies, Fixtures, Dokumentationspflege, Reviews und Closeout.
- Das [Werkzeuginventar](script-inventory.md) begründet Eigentümer,
  Aufrufer und Ersetzbarkeit jedes verbleibenden Einstiegspunkts.

## Maßgebliche Quellen

| Gegenstand | Kanonische Quelle |
| --- | --- |
| Produktstatus und öffentlicher Einstieg | `README.md` |
| Beitragsregeln | `CONTRIBUTING.md` |
| Fachlichkeit, Nutzung und Betreiberverfahren | `docs/handbook/` und `docs/portal/` |
| Planung, Umfang und Fortschritt | GitHub Issues, native Beziehungen, Milestones und Project-Felder |
| HTTP-Vertrag | FastAPI-Routen und daraus erzeugte OpenAPI-Beschreibung |
| Datenstruktur | SQLAlchemy-Modelle, `backend/db/schema.sql` und `backend/db/migrations/` |
| Qualitäts- und Releaseautomation | `Taskfile.yml` und `.github/workflows/` |
| Veröffentlichungshistorie | Tags, GitHub Releases und `CHANGELOG.md` |
| Allgemeine Historie | Git-Revisionsgeschichte |

Das [ADR-Register](decisions/index.md) enthält die langfristigen technischen
Entscheidungen und ihre Ersetzungssemantik.
Die [Python-Referenz](reference/backend.md),
[TypeScript-Referenz](reference/frontend.md), die
[Betreiber-CLI-Referenz](reference/cli.md) und das
[JSON-Schema des Vollexports](reference/full-export-v1.schema.json) sind
untergeordnete Referenzquellen und keine weiteren redaktionellen Kernbereiche.

`task docs` baut das Handbuch strikt, prüft die Registry-generierte
CLI-Referenz und erzeugt die übrigen Code-Referenzen.
Die CI stellt das Ergebnis revisionsgebunden als Artefakt
`lzug-documentation` bereit.
