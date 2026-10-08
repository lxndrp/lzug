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
`ExamLifecycleApplication` und den gemeinsamen Execution-/Planning-/Assessment-UoW.
Planning-, Assessment- und Identity-Fähigkeiten sind frameworkfreie, an den
UoW gebundene Ports. Tageszugriff, Mitgliederprojektionen und Planungsscope
werden über diese Eigentümerfähigkeiten aufgelöst. Rundeabsage verwendet
zusätzlich den Calendar-Port, um künftige Ereignisse in derselben Transaktion
zu stornieren und Empfänger für die Benachrichtigung nach dem Commit zu sammeln.
Rundenabschluss und Rundenwiederöffnung verwenden dieselbe Application-Grenze.
Der getrennte Ersatzbesetzungs-HTTP-Ablauf in `execution.absence` behält noch
direkte Planning-Zugriffe und ist für die Boundary-/Transition-Fortsetzung #1085
abgegrenzt. Schema, Datenformat und öffentliche API-Verträge bleiben unverändert.

## Transaktionsmatrix für den Prüfungs-Lifecycle

| Use Case | Aktuelle Transaktionsgrenze | Eigentümergrenze |
| --- | --- | --- |
| Prüfungstag schließen | `ExamLifecycleApplication` öffnet den gemeinsamen Execution-/Planning-/Assessment-/Identity-UoW. Execution prüft Readiness über Assessment-, Planning- und Identity-Projektionen; Tagesabschluss, Revision, Audit und Wiedereröffnungsabschluss committen gemeinsam. Benachrichtigungen folgen danach. | Gemeinsame Application-Grenze; keine zweite Lifecycle-Transaktion |
| Prüfungstag wiederöffnen | `ExamLifecycleApplication` öffnet den gemeinsamen Execution-/Planning-/Assessment-/Identity-UoW. Assessment-Korrektur, Planning-Auswirkungsprojektionen, Identity-Empfänger, Tagesrevision, Aufgaben und Audit teilen die Transaktion. Benachrichtigungen folgen nach dem Commit. | Gemeinsame Application-Grenze; keine zweite Lifecycle-Transaktion |
| Prüfungsrunde schließen oder absagen | `ExamLifecycleApplication` öffnet den gemeinsamen Execution-/Planning-/Assessment-/Identity-/Calendar-UoW. Planning-Zustände und -Zuweisungen, Assessment-Projektionen, Identity-Snapshots, Calendar-Event-Storno, Rundenentscheidung, abgeleitete Tages-/Slotzustände, Aufgaben und Audit teilen die Transaktion. Application committet atomar und stößt Benachrichtigungen danach an. | Gemeinsame Application-Grenze; fachliche Fähigkeiten kommen als gebundene Ports |
| Prüfungsrunde wiederöffnen | `ExamLifecycleApplication` öffnet den gemeinsamen Execution-/Planning-/Assessment-/Identity-UoW. Planning-Scope und Slot-/Besetzungsfakten, Assessment-Auswirkungsprojektionen, Identity-Empfänger, Runden-/Tageszustände, Aufgaben und Audit teilen die Transaktion. Benachrichtigungen folgen nach dem Commit. | Gemeinsame Application-Grenze; fachliche Fähigkeiten kommen als gebundene Ports |

Alle Close-/Cancel-/Reopen-Routen verwenden die gemeinsame Application-Grenze.
Die öffentlichen Service-eigenen Übergänge sind entfernt.
Assessment-, Planning-, Identity- und Calendar-Fähigkeiten werden als frameworkfreie,
bereits an den UoW gebundene Ports bereitgestellt; Execution bindet keine fremde
Session an Fachports und liest im beschriebenen Lifecycle-Scope keine fremden
ORM-Modelle. Der Persistence-Adapter übergibt
für Execution-eigene ORM-Regeln weiterhin die gemeinsame Session. Der getrennte
Abwesenheits-/Ersatzbesetzungsablauf bleibt eine nachgelagerte Boundary-Arbeit
#1085.
