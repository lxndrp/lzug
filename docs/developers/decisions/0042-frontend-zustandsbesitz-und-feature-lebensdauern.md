# ADR-0042: Frontend-Zustandsbesitz und Feature-Lebensdauern

## Datum

2026-10-02.

## Status

Akzeptiert.

## Kontext

Das Angular-Frontend besitzt bereits eigenständige Routen, Ports und Adapter,
hält aber noch fachlich unabhängige Daten im globalen
`ApplicationWorkspaceService` und Ablaufzustand in anwendungsweit
bereitgestellten Workflows.
Damit können Ladefehler, Rundenauswahl und Lebensdauern unabhängige Ansichten
aneinander koppeln.
Die Zielgrenzen müssen deshalb neben den vorhandenen technischen Schichten
auch Datenbesitz, Schreibrechte, Invalidierung und Übergänge festlegen.

## Entscheidung

Jedes Fachfeature besitzt seine Reads, lokalen Ansichts- und Draftzustände
sowie Commands.
Shell und Auswahlkontext halten nur anwendungsweite Navigations-, Identitäts-,
Lifecycle- und ausdrücklich ausgewählte Kontextwerte.
Dashboard ist ein eigener Konsument einer Übersicht und kein Datenlieferant
für andere Features.
Gemeinsame Referenzen werden als kleine, begründete Leseverträge geteilt;
deren Fachbesitzer und Aktualisierungsregeln bleiben sichtbar.
Fachliche Writes umfassen auch Vorschlagserzeugung und Vorschlagsspeicherung;
eine Berechnung oder Lesevorschau ist davon getrennt.
Ursprungs-IDs und Revisionen werden nur für die Felder festgehalten,
die der jeweilige Port tatsächlich entgegennimmt.
Nach erfolgreichen Writes werden abhängige Featureprojektionen gezielt
invalidiert; insbesondere bleiben Dashboard und Prüfungstag Konsumenten
bestätigter Änderungen und keine Quelle dafür.

Route- und Ansichtswechsel verwerfen ansichtsgebundene Reads, Ergebnisse und
Drafts; ein bereits gestarteter Write wird nicht durch Unsubscription als
serverseitig rückgängig behandelt.
Er darf nur dann fortleben, wenn sein Fachvertrag dies erlaubt und sein
Ursprungskontext festgehalten ist.
Rundenwechsel verwirft rundenbezogene Reads und lokale Entwürfe; laufende
Commands behalten ihre ursprüngliche Runden-ID und dürfen keinen neuen
Kontext überschreiben.
Sessionwechsel invalidiert alle geschützten Reads und Ansichten.
Abonnementabbruch ist kein Rollback.

Prüfungsorte besitzen unabhängige Venue-Reads und Venue-Commands.
Ihr Laden hängt weder von einer ausgewählten Runde noch vom Dashboard,
Planungsboard oder Stammdaten-Gesamtladen ab.
Ein erfolgreicher Orts-Command übernimmt seine bestätigte Antwort oder
invalidiert ausschließlich die Ortsdaten, die von ihm betroffen sind.
Ein Dashboard-Refresh ist dafür keine Voraussetzung.

Die Ports und Adapter markieren reale fachliche oder technische Grenzen.
Eine zusätzliche Facade, ein Use Case oder eine Klasse je API-Aufruf ist keine
Pflicht.
Öffentliche Frontend- und Backendverträge, Berechtigungen und beobachtbares
Fachverhalten bleiben bestehen.
Vorhandene Übergangspfade haben einen benannten Besitzer und werden nur im
zugeordneten Feature-Slice entfernt.

## Konsequenzen

Die Zielverantwortungen, Routezuordnung, Provider-Komposition, gemeinsame
Referenzen und Übergänge stehen im [Frontend-Architekturvertrag](../frontend-architecture-contract.md#frontend-zielvertrag).
Es trennt Ist-Kompatibilität vom Zielzustand und ordnet deren Rückbau den
Feature-Slices #1067 und #1092–#1097 zu.
Die bestehende Angular-/REST-Entscheidung in
[ADR-0004](0004-angular-rest-integration.md) bleibt für Angular Router,
REST und Featureansichten gültig; diese ADR ergänzt sie um Zustandsbesitz und
Lebensdauer.
