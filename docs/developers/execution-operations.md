# Execution-Befehle und Transaktionen

`ExecutionService` enthält die frameworkneutralen Regeln für
Anwesenheitserfassung, Slotstatus und Prüfungsstart. Seine
`ExecutionUnitOfWork`-Schnittstelle liefert materialisierte Slot-, Anwesenheits-,
Besetzungs- und Mitgliedschaftsprojektionen. Domänenbefehle und ihre Verträge
importieren weder SQLAlchemy noch FastAPI.

Die SQLite-Implementierung öffnet pro eigenständigem Schreibbefehl einen
schreibgeschützten oder schreibenden Transaktionskontext. Ein Schreibbefehl
besitzt genau eine Commit-Grenze; Unteroperationen speichern nicht selbst.
Planbestätigung, Tagesrevision, Wiederöffnungsschutz und Persistenz bleiben im
gleichen UoW.

Der Prüfungsstart prüft zunächst den bestätigten Slot, die Anwesenheit des
Prüflings und das Quorum der für diesen Slot geltenden regulären Prüfer. Es
müssen mindestens drei Mitglieder mit allen drei Vertreterseiten anwesend sein.
Identity liefert deren benötigte Mitgliedschaftsprojektion über einen
consumer-eigenen Port auf derselben Datenbanksitzung. Die Mutation setzt den
Slot auf `running`, speichert genau ein Protokoll mit den tatsächlich
beteiligten Mitgliedern und erhöht die Tagesrevision innerhalb derselben
Transaktion. Parallele Starts werden durch den schreibenden SQLite-UoW
serialisiert; ein Wiederholungsaufruf erhält das vorhandene Protokoll und
erhöht die Tagesrevision nicht erneut. Ein Fehler rollt Slot, Protokoll,
Teilnehmer und Revision gemeinsam zurück.

Anwesenheit akzeptiert weiterhin `open`, `present`, `late` und `absent`.
`late` erfordert eine Ankunftszeit; `open` und `absent` entfernen sie. Ein
inhaltlich unveränderter Write erhöht die Tagesrevision nicht. Slotstatus,
Begründung, tatsächliche Zeitangaben, erlaubte Übergänge und der Schutz
bestätigter beziehungsweise wiedergeöffneter Tage behalten den vorhandenen
Fachvertrag.

`ExamProtocolService` verwaltet Inhalt, Teilnehmende, Versionierung,
Reaktionen, Korrekturen, Berechtigungen und Aufbewahrung über einen
Execution-eigenen Port und materialisierte Snapshots.
Die FastAPI-Kante bildet Requestmodelle auf benannte Commands ab.
Execution- und Tagesmutations-Ports erhalten die erlaubten Fachfelder sowie
die erwartete Tagesrevision, nie das freie Requestmapping.
Protokoll-Exports verwenden einen strukturierten
`ProtocolReferencesSnapshot`.
Der SQLite-Adapter führt diese Operationen im selben UoW wie die zugehörigen
Tagesmutationen aus.
Die API-Kante rendert autorisierte Export-Snapshots über Presentation.
Sie ergänzt auch die HTTP-Links in API-Antworten und JSON-Exports.
`ExamDayClosureService` behält die Execution-Regeln für Tagesabschluss und
gezielte Wiederöffnung. Die FastAPI-Schreibbefehle laufen über
`ExamLifecycleApplication` und den gemeinsamen Execution-/Assessment-UoW;
der direkte Service-Aufruf bleibt vorübergehend für interne Aufrufer bestehen.
Rundenabschluss und Rundenwiederöffnung werden noch im Teilissue #1077 in
Application-Orchestrierung und Planning-, Execution- sowie Assessment-Ports
überführt. Schema, Datenformat und öffentliche API-Verträge bleiben dabei
unverändert.

## Transaktionsmatrix für den Prüfungs-Lifecycle

| Use Case | Aktuelle Transaktionsgrenze | Zielgrenze aus #1077 |
| --- | --- | --- |
| Prüfungstag schließen | Der FastAPI-Befehl läuft über `ExamLifecycleApplication` und öffnet den gemeinsamen Execution-/Assessment-UoW. Execution validiert und schreibt Abschluss, Tagesrevision, Audit und Wiederöffnungsabschluss in dessen Session; die Assessment-Readiness wird über die vom UoW gelieferte getypte Lifecycle-Fähigkeit gelesen. Application committet atomar und stößt Benachrichtigungen danach an. Der Service besitzt keinen eigenen öffentlichen Close-Befehl mehr | Gemeinsame Application-Grenze; keine weitere Lifecycle-Transaktion erforderlich |
| Prüfungstag wiederöffnen | Der FastAPI-Befehl läuft über `ExamLifecycleApplication` und öffnet den gemeinsamen Execution-/Assessment-UoW. Assessment-Korrektur, Tagesrevision, Umfang, Aufgaben und Audit verwenden dessen Session; Assessment wird über die vom UoW gelieferte getypte Lifecycle-Fähigkeit aufgerufen. Benachrichtigungen folgen nach dem Commit. Der Service besitzt keinen eigenen öffentlichen Reopen-Befehl mehr | Gemeinsame Application-Grenze; keine weitere Lifecycle-Transaktion erforderlich |
| Prüfungsrunde schließen oder absagen | Die FastAPI-Befehle laufen über `ExamLifecycleApplication` und den gemeinsamen Execution-/Assessment-UoW. Rundenentscheidung, Aufgaben, Audit und abgeleitete Tageszustände teilen dessen Session; Assessment-Projektionen kommen über die vom UoW gelieferte getypte Lifecycle-Fähigkeit. Application committet atomar und stößt Benachrichtigungen danach an. Der Service besitzt keine eigenen öffentlichen Close-/Cancel-Befehle mehr | Gemeinsame Application-Grenze; erforderliche Planning-Fähigkeiten direkt aus dem komponierten UoW beziehen |
| Prüfungsrunde wiederöffnen | Der FastAPI-Befehl läuft über `ExamLifecycleApplication` und den gemeinsamen Execution-/Assessment-UoW. Runden-, Tages-, Aufgaben- und Auditänderungen teilen dessen Session; Assessment-Auswirkungsprojektionen kommen über die vom UoW gelieferte getypte Lifecycle-Fähigkeit. Benachrichtigungen folgen nach dem Commit. Der Service besitzt keinen eigenen öffentlichen Reopen-Befehl mehr | Gemeinsame Application-Grenze; erforderliche Planning-Fähigkeiten direkt aus dem komponierten UoW beziehen |

Die vier mutierenden Close-/Cancel-/Reopen-Routen verwenden die gemeinsame
Application-Grenze. Die öffentlichen Service-eigenen Close-/Cancel-/Reopen-
Übergänge sind entfernt. Die Lifecycle-Services erhalten die bereits
sessiongebundene Assessment-Fähigkeit vom komponierten UoW, statt sie mit einer
rohen Session zu binden. Der Persistence-Adapter übergibt die gemeinsame
Session für Execution-eigene ORM-Zugriffe noch an diese Services; dieser
Übergang muss für die vollständige Portmigration weiter aufgelöst werden.
Planning-Fähigkeiten, die der Runden-Lifecycle benötigt, sind noch nicht
vollständig über den gemeinsamen UoW komponiert.
