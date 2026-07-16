# Roadmap

Stand: 16.07.2026

Dieses Dokument ordnet die ursprünglichen fachlichen Anforderungen gegen den aktuellen Projektstand ein. Es dient als fachlicher Referenzstand im Repository. Die operative Planung wird zusätzlich im GitHub Project `lzug Roadmap` gepflegt.

Die bisherige Umsetzung betrachtet im Kern den Planungsprozess einer Prüfungsrunde. Die Abwicklung des Prüfungstags selbst ist fachlich noch nicht ausgearbeitet und technisch noch nicht umgesetzt. Agil betrachtet besteht das Produkt damit aus mindestens zwei Epics:

- **Prüfungen planen**: Stammdaten, Prüflinge, Verfügbarkeiten, Planungsvorschlag, Bestätigung und nachgelagerte Terminbereitstellung.
- **Prüfungen durchführen**: Tagesansicht, Prüfungsstatus, Anwesenheiten, Protokollierung, Bewertung/Ergebnisdokumentation und Abschluss eines Prüfungstags. Dieses Epic ist noch zu spezifizieren.

## Umgesetzt

### Prüfungsrunde und Stammdaten

- **Prüfungsausschuss als Zielgruppe**: Die App ist auf Ausschussarbeit ausgerichtet, nicht auf interne IHK-Sachbearbeitung.
- **Ausschüsse und Ausschussmitglieder verwalten**: Backend-Ressourcen, Angular-Ansicht, Anlegen, Anzeigen und Aktiv/Inaktiv-Schalten sind vorhanden.
- **Rollen und Vertreterseiten modelliert**: `chair`, `deputy_chair`, `member`; `ordinary`, `deputy`; `employer`, `employee`, `school`.
- **Prüfungsorte verwalten**: Backend-Ressource, Angular-Ansicht, Anlegen, Anzeigen, Aktiv/Inaktiv-Schalten und Löschen sind vorhanden.
- **Prüflinge verwalten**: Backend-Ressource, Angular-Ansicht, Anlegen, Bearbeiten, Löschen, Suche und Fachrichtungsfilter sind vorhanden.
- **Prüflingsfelder**: Vorname, Nachname, IHK-Prüfungsnummer, Fachrichtung, Ausbildungsbetrieb, Prüfungsversuch und MEP-Pflicht sind fachlich abgebildet.
- **Fachrichtungen**: Anwendungsentwicklung, Systemintegration, Daten- und Prozessanalyse sowie Digitale Vernetzung sind abgebildet.
- **MEP- und Prüfungsversuchsvisualisierung**: Versuch und MEP werden im Frontend als sichtbare Kennzeichnungen geführt.

### Planungsgrundlagen und Verfügbarkeiten

- **Planungsparameter**: Kalenderwoche von/bis, Prüfungen pro Tag, max. Prüfungstage pro Woche, Mittagspause und Standardort sind backendseitig und im Angular-Frontend bearbeitbar.
- **Rechteprüfung für max. Prüfungstage pro Woche**: Backend prüft, dass nur ein Mitglied mit Rolle `chair` `max_exam_days_per_week` ändern darf.
- **Mögliche Prüfungstage**: Prüfungstage können manuell angelegt, aktiviert und deaktiviert oder automatisch aus einem Kalenderwochenbereich erzeugt werden. Optional werden bundesweite und landesweite Feiertage des ausgewählten Bundeslands über die kuratierte Backend-Bibliothek `holidays` ausgeschlossen.
- **Verfügbarkeiten**: Ganztägig, vormittags, nachmittags, nicht verfügbar und offen sind modelliert und in einer Angular-Matrix bearbeitbar.
- **Direktes Feedback je Verfügbarkeitszelle**: Speichern/Fehlerzustände werden im Frontend je Zelle angezeigt.

### Planungsvorschlag und Bestätigung

- **Jeder Prüfling erzeugt eine reguläre Prüfung**: Der Planungsvorschlag plant reguläre Slots aus `round_candidate`.
- **MEP-pflichtige Prüflinge erzeugen zusätzliche MEP-Slots**: MEP-Slots werden in der Planungslogik berücksichtigt.
- **MEPs am Tagesende**: Die Planungslogik platziert MEP-Slots nach regulären Slots.
- **Kein reiner MEP-Prüfungstag**: Die Planungslogik begrenzt MEP-Kapazität pro Tag auf `exams - 1`.
- **Prüfungsslot 60 Minuten**: Slotzeiten werden mit einer Stunde Dauer erzeugt.
- **Erste Prüfung 08:30 Uhr**: Slotberechnung startet um 08:30.
- **Mittagspause 12:30-13:30 optional**: Bei aktivierter Pause wird 12:30-13:30 übersprungen.
- **Besetzung je Tagesabschnitt**: Der Vorschlag wählt Arbeitgeber-, Arbeitnehmer- und Schulvertretung plus zusätzlichen Fallback.
- **Fallback nicht zugleich regulärer Prüfer desselben Abschnitts**: Die Auswahl schließt die reguläre Crew aus den Fallback-Kandidaten aus.
- **Max. Prüfungen pro Tag**: Wird über `exams_per_day` berücksichtigt.
- **Max. Prüfungstage pro Woche**: Wird in der Planungslogik berücksichtigt.
- **Planungsvorschlag bevorzugt volle Tage**: Kandidatentage werden nach Kapazität absteigend sortiert.
- **Plan bestätigen**: Backend und Frontend bestätigen Vorschläge und setzen Prüfungstage/Slots auf `confirmed`.
- **Bestätigte Termine im Dashboard**: Frontend zeigt bestätigte Termine und Statusinformationen an.
- **API-Dokumentation**: OpenAPI und Swagger-UI sind verfügbar.
- **Qualitätssicherung**: Backend-Tests, Frontend-Unit-Tests, Browser-E2E, Accessibility-Checks, Linting, Formatierung, Coverage und CI sind eingerichtet.

## Nicht abgeschlossen

### Import und Datenpflege

- **CSV-Import für Prüflinge**: Im statischen Prototyp vorhanden, im Angular-Frontend noch nicht umgesetzt.
- **Importvorlage herunterladen**: Im statischen Prototyp vorhanden, im Angular-Frontend noch nicht umgesetzt.
- **Duplikatbehandlung beim Import**: Fachlich dokumentiert, für den Angular-/Backend-Import noch nicht umgesetzt.
- **Prüfungsdurchgang bearbeiten**: Name, Rückmeldefrist und Erinnerung werden angezeigt, aber noch nicht als eigener Bearbeitungsworkflow gepflegt.

### Rechte und Sicherheit

- **Vorsitz/Stellvertretung dürfen Stammdaten und Planungsdaten bearbeiten**: Fachlich dokumentiert, aber ohne echte Authentifizierung/Rollenprüfung im Anwendungszugriff.
- **Normale Mitglieder dürfen nur Verfügbarkeiten und Ausfälle melden**: Noch nicht durch Login-/Rechtekonzept umgesetzt.
- **Benutzerkonten, Anmeldung und Sitzungen**: Datenmodell teilweise vorhanden, produktiver Authentifizierungsworkflow fehlt.

### Planung und manuelle Steuerung

- **Manuelle Übersteuerung von Planungsvorschlägen**: Fachlich als späterer Bedarf erkennbar, aber noch nicht umgesetzt.
- **Änderung bestätigter Pläne**: Bestätigte Vorschläge werden geschützt; ein kontrollierter Änderungsworkflow fehlt.
- **Kalender-/Exportansicht für bestätigte Termine**: Noch nicht umgesetzt.

### Ausfallprozess, Benachrichtigungen und Kalender

- **Ausfallmeldung eines Prüfers**: Im relationalen Schema dokumentiert, im ORM/Backend-Service und Frontend noch nicht umgesetzt.
- **Fallback-Bestätigung innerhalb von 24 Stunden**: Noch nicht umgesetzt.
- **Eskalation nach 24 Stunden**: Noch nicht umgesetzt.
- **Dringliche Anfrage bei Ausfall <36 Stunden vor Prüfungsbeginn**: Noch nicht umgesetzt.
- **Ersatzbereitschaften und Auswahl eines Ersatzprüfers**: Noch nicht umgesetzt.
- **IHK über Ausfall eines Prüfungstags informieren**: Noch nicht umgesetzt.
- **Benachrichtigungen**: Im Schema dokumentiert, aber kein Versand-/Queue-/UI-Workflow vorhanden.
- **Kalendereinladungen**: Im Schema dokumentiert, aber kein Kalenderdienst und keine Event-Erzeugung vorhanden.

### Durchführung des Prüfungstags

- **Tagesansicht für den laufenden Prüfungstag**: Noch nicht spezifiziert und nicht umgesetzt.
- **Anwesenheits- und Startkontrolle**: Noch nicht spezifiziert und nicht umgesetzt.
- **Status je Prüfung am Prüfungstag**: Noch nicht spezifiziert und nicht umgesetzt.
- **Protokollierung der Prüfung**: Noch nicht spezifiziert und nicht umgesetzt.
- **Bewertungs- oder Ergebnisdokumentation**: Noch nicht spezifiziert und nicht umgesetzt.
- **Abschluss eines Prüfungstags**: Noch nicht spezifiziert und nicht umgesetzt.
- **Nachträgliche Korrekturen oder Sperren nach Abschluss**: Noch nicht spezifiziert und nicht umgesetzt.

## Agile Einordnung

### Epic: Prüfungen planen

Status: teilweise umgesetzt.

- **Als Vorsitzender möchte ich Prüflinge, Ausschussmitglieder und Prüfungsorte pflegen, damit die Prüfungsrunde vorbereitet werden kann.** Status: umgesetzt.
- **Als Vorsitzender oder Stellvertreter möchte ich Verfügbarkeiten einsammeln, damit nur realistische Prüfungstage vorgeschlagen werden.** Status: umgesetzt.
- **Als Vorsitzender möchte ich auf Basis der Verfügbarkeiten einen regelkonformen Planungsvorschlag erzeugen, damit ich möglichst volle Prüfungstage bestätigen kann.** Status: umgesetzt.
- **Als Vorsitzender möchte ich Prüflinge importieren, damit größere Prüfungsrunden nicht manuell erfasst werden müssen.** Status: nicht abgeschlossen.
- **Als Vorsitzender möchte ich mögliche Prüfungstage aus dem Zeitraum automatisch erzeugen, damit die Vorarbeit schneller und weniger fehleranfällig ist.** Status: umgesetzt.
- **Als Vorsitzender oder Stellvertreter möchte ich bestätigte Pläne kontrolliert ändern können, damit kurzfristige Anpassungen nachvollziehbar bleiben.** Status: nicht abgeschlossen.
- **Als Ausschussmitglied möchte ich Ausfälle melden und Ersatzprozesse auslösen können, damit ein Prüfungstag möglichst nicht ausfällt.** Status: nicht abgeschlossen.

### Epic: Prüfungen durchführen

Status: nicht abgeschlossen.

Dieses Epic wurde in den ursprünglichen Anforderungen nicht näher spezifiziert. Es sollte vor der Umsetzung fachlich geschärft werden, damit die App nicht nur Termine plant, sondern den Ausschuss auch am Prüfungstag selbst unterstützt.

- **Als Ausschussmitglied möchte ich eine Tagesansicht mit allen Prüfungen, Prüflingen, Zeiten, Räumen und Besetzungen sehen, damit ich den Prüfungstag operativ durchführen kann.** Status: nicht abgeschlossen.
- **Als Ausschussmitglied möchte ich Anwesenheiten und Prüfungsstart erfassen, damit klar ist, welche Prüfungen stattfinden, verspätet sind oder ausfallen.** Status: nicht abgeschlossen.
- **Als Ausschussmitglied möchte ich den Status einer Prüfung verfolgen, damit der Ausschuss sieht, ob eine Prüfung offen, laufend, abgeschlossen oder nachzubereiten ist.** Status: nicht abgeschlossen.
- **Als Ausschussmitglied möchte ich prüfungsbezogene Notizen oder Protokolldaten erfassen, damit die Durchführung nachvollziehbar dokumentiert ist.** Status: nicht abgeschlossen.
- **Als Vorsitzender möchte ich Ergebnisse oder Abschlussinformationen strukturiert festhalten, damit der Prüfungstag formal abgeschlossen werden kann.** Status: nicht abgeschlossen.
- **Als Vorsitzender möchte ich den Prüfungstag abschließen und danach Änderungen begrenzen, damit dokumentierte Ergebnisse verlässlich bleiben.** Status: nicht abgeschlossen.

## Projektplan

### Phase 1: Epic Prüfungen planen - Import und Planungsgrundlagen abschließen

- CSV-Import für Prüflinge im Angular-Frontend und Backend-Service umsetzen.
- Importvorlage als Download bereitstellen.
- Duplikate anhand der IHK-Prüfungsnummer beim Import erkennen und berichten.
- Backend-Endpunkt und Frontend-Aktion zum Erzeugen möglicher Prüfungstage aus KW von/bis ergänzen. Status: umgesetzt.
- Prüfungsdurchgang-Bearbeitung für Name, Rückmeldefrist und Erinnerung umsetzen.

### Phase 2: Epic Prüfungen planen - Rechte und Benutzerkonzept

- Authentifizierung einführen.
- Rollenprüfung serverseitig für Stammdaten, Planungsdaten und Verfügbarkeiten erzwingen.
- Frontend-Aktionen abhängig von Rolle und Status aktivieren/deaktivieren.
- Testfälle für Vorsitz, Stellvertretung, ordentliches Mitglied und stellvertretendes Mitglied ergänzen.

### Phase 3: Epic Prüfungen planen - Planung nach Bestätigung operationalisieren

- Kontrollierten Workflow zum Ändern bestätigter Pläne definieren und implementieren.
- Manuelle Anpassungen an Prüfungstagen, Slots und Besetzungen ermöglichen.
- Kalender-/Exportansicht für bestätigte Termine ergänzen.
- Tests für Statusübergänge und Änderungsgrenzen erweitern.

### Phase 4: Epic Prüfungen planen - Ausfallprozess

- ORM-Modelle und Repositories für `absence_report`, `replacement_response`, `notification` und `calendar_event` ergänzen.
- Ausfallmeldung im Frontend umsetzen.
- Fallback-Bestätigung, 24h-Eskalation und <36h-Dringlichkeitsprozess implementieren.
- Ersatzabfrage, Ersatzwahl und IHK-Ausfallinformation umsetzen.
- Benachrichtigungsereignisse persistieren und später an Versandkanäle anbinden.

### Phase 5: Epic Prüfungen planen - Benachrichtigungen und Kalenderintegration

- Benachrichtigungsversand als austauschbare Schnittstelle anbinden.
- Kalenderereignisse für bestätigte, geänderte und abgesagte Termine erzeugen.
- Externe Kalenderdienst-Integration auswählen und implementieren.
- Monitoring und Fehlerbehandlung für Versand und Kalender-Synchronisation ergänzen.

### Phase 6: Epic Prüfungen durchführen - Fachliche Spezifikation

- Ablauf eines Prüfungstags mit Vorsitz, Prüfern, Prüflingen und Orten beschreiben.
- Zustände für Prüfungstag und einzelne Prüfung definieren.
- Benötigte Protokoll-, Bewertungs- und Abschlussdaten klären.
- Grenzen zwischen Ausschussunterstützung und IHK-interner Sachbearbeitung festlegen.
- User Stories und Akzeptanzkriterien für die Durchführung priorisieren.

### Phase 7: Epic Prüfungen durchführen - Umsetzung

- Tagesansicht für laufende und bevorstehende Prüfungen umsetzen.
- Anwesenheits-, Start-, Pausen-, Abschluss- und Ausfallstatus je Prüfung abbilden.
- Protokoll- und Ergebnisdatenmodell ergänzen.
- Backend-REST-Ressourcen und Frontend-Workflows für die Durchführung umsetzen.
- Sperr- und Korrekturworkflow nach Abschluss eines Prüfungstags ergänzen.
- Tests für Statusübergänge, Rechte und Abschlusslogik ergänzen.

## Pflegehinweis

- Statusänderungen an Anforderungen sollen in diesem Dokument nachvollziehbar bleiben.
- Operative Aufgaben werden im GitHub Project `lzug Roadmap` gepflegt und mit Issues im Repository verknüpft.
