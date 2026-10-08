# ADR-0041: Backend-Modulverantwortung und Use-Case-Verträge

## Datum

2026-10-02.

## Status

Akzeptiert.

## Kontext

Das Backend ist ein synchroner modularer Monolith mit einem autoritativen
Prozess, SQLite und SQLAlchemy.
Die schrittweise Aufteilung hat Fachregeln aus HTTP-Routen und einem
generischen Repository in eigene Planungs-, Ausführungs-, Bewertungs- und
Identitätsmodule verschoben.
Ohne verbindliche Ownership und Transaktionsgrenzen drohen doppelte Regeln,
unbeabsichtigte Abhängigkeiten und Commits innerhalb eines Use Cases.

## Entscheidung

Die Zielverantwortungen, Modulabhängigkeiten, Ports, Lebensdauern,
Transaktionsgrenzen und Migrationsreihenfolge stehen im
[Backend-Vertrag](../backend-architecture-contract.md).
Er ist der verbindliche Implementierungsvertrag für Backend-Aufteilung und
Portmigration.

Die Fachmodule `planning`, `execution`, `assessment` und `identity` besitzen
ihre Regeln und öffentlichen Use Cases.
Kandidaten, Rundenzuordnung, Rundenentscheidungen und Prüfungszeiträume gehören
zu `planning`; Tages-/Slotfolgen und Wiederöffnungsaufgaben zu `execution`;
Ergebnisstatus und Ergebnisrevisionen zu `assessment`.
Ein benötigtes Prüfungs-Halbjahr wird im Planning-UoW gemeinsam mit seiner
Runde angelegt; eigenständige Halbjahres-Update-/Delete-Commands gehören nicht
zum Vertrag.
Konten, Personen und Mitgliedschaften zu `identity`.
`application` koordiniert ausschließlich Use Cases über Fachgrenzen hinweg
und deren gemeinsame Transaktionen.
Ein universelles Ressourcenrepository oder ein generischer gemeinsamer
Vertragsbereich wird nicht eingeführt.

`calendar`, `notifications` und `documents` sind eigenständige unterstützende
Module.
`integrations` enthält konkrete externe Adapter.
`calendar` besitzt Feed-Credentials, die lokal persistierte
`CalendarEvent`-Projektion und die ICS-Ausgabe.
Der heutige Legacy-Pfad `integrations.calendar` enthält die Projektion und
deren Materialisierung; Planning besitzt die Planfolgen und speichert
Kalenderaufträge mit der bestätigten Planrevision.
Calendar materialisiert die lokale Projektion danach wiederholbar in einem
eigenen Datenbank-UoW und Planning bestätigt den Auftrag mit Event-ID und
Eventversion in einem weiteren Planning-UoW.
Ein späterer Payloadfehler rollt alle früheren Projektionsänderungen desselben
Runden-Syncs zurück; diese All-or-nothing-Grenze ist Teil des Zielvertrags.
Venuefolgen gehören ebenfalls zu Planning. Execution besitzt Abwesenheits-
und Rundenstorno-Folgen. Application führt alle Kalenderfolgen über denselben
Calendar-Service-Port nach dem jeweiligen Fach-Commit aus und besitzt den
dauerhaften Folgeauftragszustand mit stabiler Ursprungsidentität, Claim, Retry
und Ergebnis. Ein fehlgeschlagener Kalender-UoW setzt den Fach-Commit nicht
zurück und lässt die Folgearbeit wiederholbar offen.
Planning leitet typisierte Plan- und Ortsfolgen aus materialisierten
Änderungssnapshots ab. `application.plan_consequences` und
`application.venue_consequences` koordinieren die unabhängigen Folgeaktionen;
`persistence.application_consequences` besitzt den dauerhaften Batch- und
Taskzustand. Der bestehende Tabellenvertrag bleibt erhalten.
Nach einem Neustart stößt der bestehende Admin-Processing-Command den
Re-Drive aus unveränderlichen Domainquellen an; ein automatischer
Startup-Hook oder Hintergrundworker ist nicht vorausgesetzt.
Er leitet fehlende Venue-Batches aus versionierten Auditereignissen erneut ab
und verarbeitet persistierte fällige Tasks; abgelaufene Venue-Claims bleiben
im Betreiberpfad sichtbar und wiederholbar.
Plan-Notifications prüfen die neueste bestätigte Revision, supersedieren
unzugestellte ältere Notices und speichern die aktuelle Notice atomar in einer
serialisierten Notification-UoW.
Eventgenerationen sind im aktuellen Code in `source_key` und
`external_event_id` codiert; Inhaltsänderungen behalten die Identität und
erhöhen die Eventversion, eine Reaktivierung erzeugt eine weitere Generation.
`list_events`, `feed_ics` und `event_ics` synchronisieren vor dem Read oder
Rendern; nur `feed_ics` validiert ein Feed-Credential und Refresh und Read
verwenden getrennte Session-Scopes.
Der Ablauf enthält keinen Provider-Claim oder Provider-I/O.
Das bestätigte Ziel aus [Issue #1078](https://github.com/lxndrp/lzug/issues/1078)
ist, stabile Identitäten und Generationen über Wiederholungen und Planänderungen
sowie die Sync-Seiteneffekte der Reads zu erhalten.
`calendar` bezieht bestätigte Planungsdaten über einen eigenen typisierten
Snapshot-Port, den ein Planning-Adapter erfüllt.
Das bestätigte Ziel aus [Issue #1081](https://github.com/lxndrp/lzug/issues/1081)
belässt die Ableitung fachlicher Folgen in Planning und überträgt ihre
Ausführung an `application`.
Application definiert den von seinen Folge-Use-Cases konsumierten
Calendar-Service-Port und die Ports/Wertverträge für Taskzustand.
Calendar und Persistence liefern strukturell passende Ergebnisse; Application
speichert Taskabschluss oder Retry im eigenen consumer-eigenen UoW.
Für einen Human-Export gibt Application einen vollständig autorisierten,
materialisierten Snapshot zurück; der HTTP-Adapter ruft nach dem UoW den reinen
Renderer `presentation.exam_exports` auf.
`application` hängt nicht von `presentation` ab.
Der Composition Root verdrahtet Snapshot-Port, Planning-Adapter und
Application-Port.
Application liest abgeschlossene Eventgenerationen über den öffentlichen
Calendar-Service-Port; die Orchestrierung liest keine `CalendarEvent`-Modelle.
Application revalidiert den Task-Claim unmittelbar vor dem Seiteneffekt und
schreibt Abschluss oder Fehlerstatus nur unter dem gespeicherten Leasewert.
Externe Kalender-/Notification-Effekte bleiben nicht Exactly-once.
Execution besitzt einen eigenen engeren Calendar-Port für Lifecycle-Syncs.
Ein konsumierendes Modul definiert ein kleines strukturelles `Protocol` für
die benötigte Fähigkeit.
Ein zusätzliches Interface für lokale Services entsteht nur bei belegtem
Entkopplungsnutzen.

Commands, Ergebnisse und materialisierte Snapshots verwenden bei Bedarf
typisierte Dataclasses, Enums und Unions.
ORM-Modelle werden nicht flächendeckend dupliziert.
Domänentypen gehören ihrem fachlichen Eigentümer; einen globalen
`contracts`-, `common`- oder `utils`-Eimer gibt es nicht.
`Session`, `Query`, SQL-Ausdrücke, `Resource.model` und lazy ORM-Werte
überschreiten nicht die Persistenzgrenze.

Explizite Context Manager und UoW-Factories drücken Transaktionen aus.
Verbraucher-Ports beschreiben domänenspezifische Transaktionskontexte und
reichen keine SQLAlchemy-Session durch.
Konkrete Persistence-Adapter können intern dieselbe Session teilen;
Unteroperationen führen keinen eigenen Commit aus.
Eine sichtbare Composition Root verdrahtet Konfiguration, Runtime,
Persistenzpfade, Ports, Adapter und Lebensdauern.
HTTP- und Admin-Wire-Verträge, Mapping und Fehlerübersetzung bleiben am
jeweiligen Adapterrand.
`presentation` rendert ausschließlich freigegebene, materialisierte Werte
und besitzt keine Persistenz- oder Fachlogik.

`operations` besitzt technische Instanz- und Wartungsverträge.
Backup und Migration behalten ihre SQLite-spezifischen Konsistenz- und
Dateigarantien; sie werden nicht als portabler generischer Datenbankvertrag
modelliert.

Bestehende Middleware, Runtime-Zulassung, ContextVars sowie Session- und
Sperrmanager bleiben explizite Erweiterungspunkte.
Gemeinsames technisches Error-Mapping oder nachweislich duplizierte
Admin-Orchestrierung darf mit `contextlib`, kleinen Wrappern und bei Bedarf
`functools.wraps` zusammengefasst werden.
Querschnittliche Fachregeln bleiben im jeweiligen Use Case sichtbar.
Es gibt keine AOP-/DI-/Repository-Infrastruktur, dynamisches Weaving,
globale Interception oder pauschale Transaktions-, Retry-, Autorisierungs-
und Response-Filter-Aspekte.

## Konsequenzen

- Die bestehenden HTTP-, OpenAPI- und Admin-Verträge, Demo-Isolation und
  migrationskompatiblen Daten bleiben erhalten.
- Jeder Port nennt einen konsumierenden Eigentümer, beobachtbares Verhalten,
  Fehler und UoW-Beteiligung.
- Revision-CAS, Audit, Wiederöffnung, veraltete Exporte,
  Ergebnisoffenlegung, Retry-Entscheidungen und Runtime-Sperren bleiben
  explizite Use-Case-Schritte.
- Externe Fehler rollen bereits bestätigte Fachänderungen nicht zurück.
  Zustellung wird nicht als Exactly-once-Zustellung ausgegeben.
- Der Übergang erfolgt schrittweise über benannte Kompatibilitäts- und
  Persistenzadapter; Eigentümer und Entfernungskriterien stehen im
  Backend-Vertrag.

## Referenzen

- [ADR-0002: Python-Backend mit SQLAlchemy](0002-python-backend-sqlalchemy.md)
- [ADR-0008: Kuratierte Feiertagsdaten über einen Provider](0008-feiertagsprovider.md)
- [ADR-0027: Synchroner FastAPI-Kern für die schrittweise HTTP-Migration](0027-synchroner-fastapi-migrationskern.md)
- [ADR-0033: AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen](0033-aio-betrieb-admintransport-und-lifecycle.md)
- [Backend-Vertrag](../backend-architecture-contract.md)
