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
| Prüfungstag schließen | Application öffnet den Composite-UoW, lädt detached Planning-, Assessment- und Identity-Fakten und übergibt sie der Execution-Regelprüfung. Danach wendet Application den Execution-eigenen Abschluss samt Revision, Audit und Wiedereröffnungsabschluss an. Benachrichtigungen folgen nach Commit. | Application besitzt Reihenfolge und gemeinsame Commit-Grenze |
| Prüfungstag wiederöffnen | Application lädt Scope- und Auswirkungsfakten, Execution validiert den Reopen-Intent, Assessment öffnet die betroffenen Korrekturen, danach schreibt Execution Aufgaben und Audit. Alle Schritte teilen den UoW; Benachrichtigungen folgen nach Commit. | Application besitzt Reihenfolge und gemeinsame Commit-Grenze |
| Prüfungsrunde schließen oder absagen | Application lädt Planning-, Assessment- und Identity-Fakten, Execution validiert den Intent, Planning führt Revision-CAS aus. Bei Absage storniert Application zusätzlich Planning-Slots und Calendar-Ereignisse. Execution schreibt Entscheidung, Tageszustände und Audit. Benachrichtigungen folgen nach Commit. | Application besitzt Reihenfolge und gemeinsame Commit-Grenze |
| Prüfungsrunde wiederöffnen | Application lädt Scope- und Auswirkungsfakten, Execution validiert den Intent, Planning führt Revision-CAS aus und Execution schreibt Wiederöffnung, Aufgaben, Exportinvalidierung und Audit. Benachrichtigungen folgen nach Commit. | Application besitzt Reihenfolge und gemeinsame Commit-Grenze |

Alle Close-/Cancel-/Reopen-Routen verwenden die gemeinsame Application-Grenze.
Die öffentlichen Service-eigenen Übergänge sind entfernt.
Assessment-, Planning-, Identity- und Calendar-Fähigkeiten werden als frameworkfreie,
bereits an den UoW gebundene Ports bereitgestellt; Execution bindet keine fremde
Session an Fachports und liest im beschriebenen Lifecycle-Scope keine fremden
ORM-Modelle. Der Persistence-Adapter übergibt
für Execution-eigene ORM-Regeln weiterhin die gemeinsame Session. Der getrennte
Abwesenheits-/Ersatzbesetzungsablauf bleibt eine nachgelagerte Boundary-Arbeit
#1085.
