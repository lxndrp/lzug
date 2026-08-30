# Revisionierte Planänderung

Eine bestätigte Planung bleibt bis zum tatsächlichen Start eines ihrer Slots
als vollständiges Plan-Aggregat bearbeitbar.
Vorsitz und Stellvertretung benötigen dafür Ausschuss-Verwaltungsrechte,
einen aktuellen Revisionsstand und einen nicht leeren Änderungsgrund.

`GET` und `PUT /api/exam-rounds/{id}/confirmed-plan` liefern beziehungsweise
ändern ausschließlich das gesamte Aggregat aus Prüfungstagen, Slots und
Besetzungen.
Die generischen Schreibpfade für diese Objekte bleiben gesperrt.
`GET /api/exam-rounds/{id}/confirmed-plan/revisions` liefert die
unveränderliche Historie mit Akteur, Zeitpunkt, Grund sowie vollständigem
Vorher- und Nachher-Zustand.

Die serverseitige Normalisierung leitet Reihenfolge und Zeiten aus dem
gewählten Kandidatentag ab und prüft weiterhin alle Planungsregeln für Ort,
Prüflinge, Besetzung, Verfügbarkeit, Fallback und Kapazität.
Ein gestarteter, abgeschlossener oder abgesagter Slot beziehungsweise Tag
sperrt die Änderung mit HTTP 409.
Ein veralteter Gesamtplanstand führt ebenfalls zu HTTP 409.

Die Änderung behält vorhandene Tages-, Slot- und Besetzungsidentitäten bei.
Benachrichtigungen und persönliche Kalender werden erst nach dem erfolgreichen Commit über [eigene, wiederholbare Folgenvorgänge](plan-change-consequences.md) aktualisiert.
Ein Folgenfehler kann die bestätigte und auditierte Planrevision nicht zurückrollen.
