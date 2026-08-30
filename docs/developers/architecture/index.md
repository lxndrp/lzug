# Architekturgrundlage

`lzug` ist ein modularer Monolith für die Arbeit eines Prüfungsausschusses.
Die Architekturgrundlage ordnet den aktuellen Stand nach den für das Projekt relevanten arc42-Blickrichtungen, ohne eine vollständige arc42-Schablone oder eine zweite technische Referenz zu pflegen.
Ausführbarer Code, Schema, Migrationen, OpenAPI, Containerverträge und Workflows bleiben für ihre Details maßgeblich.

## Orientierung

| arc42-Blickrichtung | Leitfrage | Kanonische Quelle |
| --- | --- | --- |
| Ziele und Randbedingungen | Welche Leitplanken begrenzen Änderungen? | [Architekturprinzipien](principles.md) |
| Kontext und Abgrenzung | Wer nutzt `lzug`, und welche externen Systeme werden berührt? | [Systemkontext](views.md#systemkontext) |
| Lösungsstrategie und Bausteine | Wie bleibt der modulare Monolith gegliedert? | [Container-Sicht](views.md#container-sicht) und [Backend-Grenzen](backend.md) |
| Laufzeit | Wie durchläuft eine kritische Änderung Sicherheits-, Fach- und Persistenzgrenzen? | [Kritischer Ablauf](views.md) und die fachlichen Architekturseiten |
| Verteilung | Was läuft in Browser, OCI-Container und persistentem Datenbereich? | [Deployment-Sicht](views.md#deployment-sicht) und [OCI-Runtime](oci-runtime.md) |
| Querschnittliche Konzepte | Wo liegen Identität, Daten, Oberfläche und Betrieb? | [Authentifizierung](authentication.md), [Datenmodell](../domain-model.md), [Datenbankschema](../database-schema.md) und [Frontend-Richtlinie](../frontend-guidelines.md) |
| Entscheidungen | Warum wurde eine langfristige Richtung gewählt? | [ADR-Register](../decisions/index.md) |
| Qualität und Risiken | Welche Risiken müssen Änderungen sichtbar behandeln? | [Reviewkriterien](../reviews/kriterien.md) |

## System- und Fachgrenzen

Das Angular-Frontend ist das Arbeitswerkzeug für Ausschussmitglieder.
Der produktive FastAPI-Adapter vermittelt zwischen Browser und den frameworkfreien Anwendungsservices; SQLAlchemy-Modelle, Repositories und Migrationen halten den lokalen Zustand in SQLite.
Die Self-Hosting-Instanz gehört genau einem Ausschuss.
Betreiberrechte und die lokale [Betreiber-CLI](operator-auth-cli.md) erzeugen keine fachliche Ausschussrolle.
Vertiefte Systemdiagnose bleibt ebenfalls an diese lokale Betriebsgrenze gebunden.

Der [Lebenszyklus einer Prüfungsrunde](exam-round-lifecycle.md) beschreibt den ausschussbezogenen Abschluss, die vollständige Absage, die zentrale Sperre, gezielte Wiederöffnungen und revisionsgebundene Nachweise.
[Benachrichtigungen](notifications.md), [Kalenderfolgen](plan-change-consequences.md) und andere technische Integrationen bleiben von dem auslösenden Fachvorgang getrennt.
Der frühe Prototyp unter `prototypes/pruefungsrunde-prototyp/` ist keine Produktlaufzeit.

Die aktuelle technische Quelle liegt jeweils beim ausführbaren Vertrag:

- HTTP-Routen und OpenAPI-Antwortmodell: `backend/fastapi_app.py`; Start und
  Transportgrenzen: `backend/server.py` und `backend/transport.py`.
- Datenstruktur und Weiterentwicklung: `backend/models.py`, `db/schema.sql`
  und `db/migrations/`.
- Produktversion: die beim Build erzeugte `build-metadata.json`; sie leitet
  die Identität aus Commit und gegebenenfalls Release-Tag ab.
- Betriebs-, Sicherheits- und Qualitätsgrenzen: Dockerfiles, Compose-Datei,
  Taskfile und Workflows.

## Lösungsstrategie und bewusste Grenzen

- Frontend, HTTP-Adapter, Anwendungskern und Persistenz bleiben klar getrennte
  Verantwortungen innerhalb eines modularen Monolithen.
- Das OCI-Image fasst Browser-Bundle und Python-Anwendung für eine einfache
  Self-Hosting-Instanz zusammen; `/data` ist ihr einziger dauerhafter Bereich.
- Die öffentliche Demo ist eine getrennte flüchtige Assembly und kein
  Produktions- oder Self-Hosting-Muster.
- Externe Zustellkanäle sind optional und best effort.
  Ihr Ausfall macht einen
  bereits erfolgreichen Fachvorgang nicht rückgängig.
- Microservices, Kubernetes, eine zentrale Mandantenplattform und eine
  zusätzliche Architektur-Governance sind nicht Teil des aktuellen Systems.
  Eine langfristige Richtungsänderung benötigt einen nachvollziehbaren ADR.

## Detaillierte Facharchitektur

Die [Backend-Übersicht](backend.md) ordnet die produktiven Services ihren Schichten zu.
[Authentifizierung](authentication.md), [Benachrichtigungen](notifications.md), der [Ausfall- und Ersatzprozess](absence-replacement.md), die [Prüfungsprotokolle](exam-protocols.md), [Bewertungen und Ergebnisse](exam-results.md), die [revisionierte Planänderung](confirmed-plan-revisions.md), deren [nachgelagerte Benachrichtigungs- und Kalenderfolgen](plan-change-consequences.md) sowie der [formelle Tagesabschluss](exam-day-closure.md) beschreiben die fachlichen Verantwortungsgrenzen.
Das [fachliche Datenmodell](../domain-model.md) erläutert Begriffe, Aggregate und Invarianten; es ersetzt kein Schema.
[Backup, Restore und Vollexport](backup-restore-export.md) beschreibt konsistente Snapshots, den geschützten Artefaktvertrag und die lokale Restore-Grenze.
Diese Funktionen verwenden die lokale [Betreiber-CLI-Grenze](operator-auth-cli.md) und sind nicht Teil der HTTP-API.

`GET /api/health` ist ein reines Liveness-Signal des laufenden Prozesses.
`GET /api/ready` prüft die Anwendungs- und Datenbankbereitschaft und liefert HTTP 200 beziehungsweise HTTP 503.
Die vollständigen Maschinenverträge gehören zur OpenAPI-Quelle; diese Übersicht wiederholt sie nicht.

Die langfristigen Entscheidungen stehen im [ADR-Register](../decisions/index.md).
Jeder ADR folgt dem durch [ADR-0029](../decisions/0029-einheitliches-nygard-format.md) verbindlich festgelegten Nygard-Format.
ADRs erklären die gewählte Richtung, nicht aktuelle Endpunkt-, Feld- oder Workflowdetails.
