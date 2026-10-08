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
Der SQLite-Adapter führt diese Operationen im selben UoW wie die zugehörigen
Tagesmutationen aus.
Die API-Kante rendert autorisierte Export-Snapshots über Presentation.
Auch Tagesabschluss und gezielte Wiederöffnung bleiben in
`ExamDayClosureService`; deren fachübergreifende Orchestrierung wird im
dafür vorgesehenen Teilissue #1077 in Planning-, Execution- und
Assessment-Ports mit einem gemeinsamen UoW überführt.
Dieser Schritt ändert weder Schema und Datenformat noch öffentliche
API-Verträge.
