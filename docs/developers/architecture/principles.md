# Architekturprinzipien

Diese Prinzipien sind verbindliche Leitplanken für Änderungen am aktuellen System.
Sie beschreiben keine neue Freigabestufe: Pull Request, vorhandene Reviews und risikoproportionale Prüfungen bleiben der Umsetzungsweg.
Ein ADR dokumentiert eine langfristige neue oder ablösende Richtung; das vollständige Register steht unter [Architekturentscheidungen](../decisions/index.md).

1. **Modularer Monolith vor verteilter Komplexität.** Fachliche Module bleiben
   im gemeinsamen Anwendungskern klar getrennt, solange eine unabhängige
   Auslieferung keinen belegten Nutzen hat.
   Microservices und zusätzliche
   Netzwerkgrenzen sind keine Standardlösung.
2. **Eine Instanz, ein Ausschuss, ein lokaler Betriebsbereich.** Ausschussdaten
   und fachliche Rollen bleiben instanzbezogen; Betreiberrechte ersetzen keine Mitgliedschaft.
   Das OCI-Einzelcontainer-Modell und `/data` bilden die
   bewusste Self-Hosting-Grenze ([ADR-0013](../decisions/0013-dezentrale-instanzen-je-ausschuss.md), [ADR-0014](../decisions/0014-oci-einzelcontainer-und-persistentes-data.md)).
3. **Verträge sind an jeder Außengrenze explizit.** OpenAPI, das versionierte
   Admin-JSON-Protokoll, OCI-Konfiguration, Schema und Migrationen sind
   überprüfbare Verträge.
   Clients oder Adapter umgehen sie nicht
   ([ADR-0006](../decisions/0006-openapi-http-vertrag.md), [ADR-0021](../decisions/0021-goreleaser-fuer-die-betreiber-cli.md)).
4. **Der Anwendungskern bleibt von Adaptern unabhängig.** HTTP, Persistenz,
   Benachrichtigung und Kalender übersetzen an klaren Grenzen.
   Fachlogik bleibt
   in synchronen, frameworkfreien Services und wird nicht in Handlern oder
   Integrationen dupliziert.
5. **Datenhaltung entwickelt sich vorwärts und erhält Nachweise.** Schemaänderungen
   verwenden geordnete Migrationen und kompatible Übergänge.
   Fachlich relevante
   Korrekturen, Versionen und Entscheidungen überschreiben frühere Stände nicht
   stillschweigend ([ADR-0001](../decisions/0001-lokale-relationale-persistenz.md), [ADR-0002](../decisions/0002-python-backend-sqlalchemy.md)).
6. **Sicherheitsgrenzen sind serverseitig und fail-closed.** Identität, CSRF,
   Ausschuss-Scope, Rollen, Betreiberzugriff, Uploads und Runtime-Konfiguration
   werden an der kontrollierenden Grenze validiert.
   Clientfelder, UI-Zustand
   und Betreiberrechte sind kein fachlicher Berechtigungsnachweis.
7. **Externe Integrationen gefährden keinen bestätigten Fachzustand.** Kalender,
   Push und E-Mail sind idempotent oder best effort entkoppelt.
   Fehler werden
   sichtbar und wiederholbar behandelt, rollen aber einen bereits atomar
   bestätigten Fachvorgang nicht rückwirkend zurück.
8. **Personenbezogene Daten werden minimiert und Änderungen bleiben nachvollziehbar.**
   Schnittstellen, Logs, Diagnosen, Kalender und Benachrichtigungen geben nur
   den für Empfänger und Zweck nötigen Inhalt aus.
   Kritische Zustandsänderungen
   tragen Actor, Zeitpunkt, Grund oder Revision, soweit der Fachvertrag dies
   verlangt.
9. **Jeder Gegenstand hat eine maßgebliche Quelle.** Code und deklarative
   Verträge bestimmen ausführbares Verhalten, ADRs langfristige Entscheidungen,
   das Entwicklerhandbuch aktuelle Orientierung und das Wiki redaktionelle
   Anleitungen.
   Übersichten verlinken Details, statt sie als zweite Referenz zu
   kopieren ([ADR-0007](../decisions/0007-dokumentation-und-code-referenz.md), [ADR-0012](../decisions/0012-wiki-single-source-of-truth.md)).
10. **Prüftiefe folgt Risiko und Auswirkungsbreite.** Eng begrenzte Änderungen
    erhalten fokussierte Nachweise; Änderungen an Verträgen, Sicherheit,
    Migrationen, Toolchain oder mehreren Schichten benötigen breitere Prüfungen.
    Grüne Automation ergänzt das Architektur- und Fachreview, ersetzt es aber
    nicht.

Die [risikobasierte Architekturprüfung](../reviews/kriterien.md) übersetzt diese Leitplanken in kurze Reviewfragen.
