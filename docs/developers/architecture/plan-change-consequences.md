# Folgen bestätigter Planänderungen

Eine bestätigte Planrevision bleibt der maßgebliche fachliche Stand.
Benachrichtigungs- und Kalenderfolgen werden erst nach dem Commit der unveränderlichen Revision abgeleitet und in eigenen Vorgängen verarbeitet.
Ein Fehler dieser Vorgänge rollt die Planänderung deshalb nicht zurück.

`PlanConsequenceService` vergleicht ausschließlich den gespeicherten Vorher- und Nachher-Snapshot aus `confirmed_plan_revision`.
Eine Änderung von Zeit, Ort, eigener Rolle oder Einplanung erzeugt eine persönliche Kalenderfolge.
Ein Personentausch storniert das Ereignis der entfernten Person und legt für die neue Person eine neue Ereignisidentität an.
Die verbleibende Besetzung erhält nur eine zusammengefasste interne Nachricht, solange ihr eigenes Kalenderereignis unverändert bleibt.
Die handelnde Person erhält keine redundante Nachricht.
Eine reine Änderung von Grund, Reihenfolge oder anderen nicht kalenderwirksamen Angaben erzeugt keine Folge.

`plan_consequence_batch` hält die wiederholbare Ableitung eines unveränderlichen fachlichen Ursprungs über `origin_type` und `origin_key` fest.
Für Planänderungen verweist er zusätzlich auf die bestätigte Revision; weitere Ursprungsvorgänge können denselben Folgenvertrag verwenden, ohne eine Planrevision vorzutäuschen.
`plan_consequence` enthält pro Empfänger und fachlicher Identität genau eine Benachrichtigungs- oder Kalenderfolge mit Zustand, Versuchszahl und datensparsamer Fehlerkennung.
Die Zustände sind `pending`, `succeeded`, `temporarily_failed`, `permanently_failed` und `superseded`.
Vorübergehende Fehler verwenden begrenzte exponentielle Wiederholungen; ein manueller Wiederanstoß setzt nur fehlende oder fehlgeschlagene Folgen der weiterhin aktuellen Revision zurück.

Eine ältere Revision darf den aktuellen Planstand nicht überschreiben.
Noch offene ältere Folgen derselben Empfänger- oder Kalenderidentität werden durch eine tatsächlich überholende neuere Änderung auf `superseded` gesetzt.
Bleibt eine ältere Folge trotz einer späteren nicht wirksamen Revision fachlich aktuell, verarbeitet sie immer den heutigen Sollstand und darf deshalb weiterhin wiederholt werden.
Bereits intern wirksame Kalenderstände werden von der neueren Revision unter derselben persönlichen Ereignis-ID und mit höherer Version korrigiert.
Noch unversuchte interne Nachrichten werden ausgeblendet und technisch als überholt beendet; bereits versuchte oder bestätigte Nachrichten bleiben nachvollziehbar.

Vorsitz und Stellvertretung lesen den inhaltsfreien Folgenstatus über `GET /api/exam-rounds/{id}/confirmed-plan/consequences` und stoßen zulässige Wiederholungen revisionsbezogen an.
Mitglieder sehen weiterhin nur ihre eigenen Nachrichten und Kalenderereignisse.
Betreiber lesen den inhaltsfreien technischen Nachweis mit `lzug-admin plan-consequences-status --revision-id <id>` und verwenden `lzug-admin retry-plan-consequences --revision-id <id>` für einen Wiederanstoß.
Die Ausgabe enthält ausschließlich technische Kennungen, Zeitpunkte, Zähler, Zustände und Fehlercodes.
`lzug-admin process-notifications` verarbeitet zusätzlich automatisch fällige Folgenwiederholungen.

Migration `022_add_plan_consequences.sql` erhält vorhandene Nachrichten, Zustellungen und Kalenderereignisse unverändert.
Sie markiert vorhandene Revisionen als bewusst nicht nachträglich abgespielt und erzeugt für sie keine neuen Nachrichten.
Fehlende Folgen einer weiterhin aktuellen Revision können kontrolliert durch den fachlichen oder technischen Wiederanstoß abgeleitet werden.
