# Datenbankschema

`db/schema.sql` ist die ausführbare Referenz für eine neue Datenbank.
`db/migrations/` ist die chronologische Referenz für Änderungen bestehender Bestände; die Laufzeit prüft ihre Historie und Integrität.
SQLAlchemy-Modelle unter `backend/models.py` bilden dieselbe Produktstruktur in der Anwendung ab.

Diese Quellen sind gemeinsam maßgeblich.
Generierte Code-Referenzen entstehen beim Dokumentationsbuild.
Die Entscheidung für lokale relationale Persistenz hält [ADR-0001](decisions/0001-lokale-relationale-persistenz.md) fest.

Diese Seite enthält bewusst keine Tabellen-, Feld- oder Typliste. Änderungen
am Datenmodell erfolgen über Modell, Schema und erforderliche Migration
zusammen; ihre fachliche Bedeutung erläutert das
[fachliche Datenmodell](domain-model.md).

Die Migration `017_add_exam_protocols.sql` legt bei der Bestandsübernahme nur
für bereits gestartete, noch laufende oder nachzubereitende Slots einen leeren,
offenen Protokollstand und den aus Anwesenheit sowie Tagesabschnitt ermittelten
Beteiligten-Snapshot an. Sie erfindet weder für abgeschlossene historische
Prüfungen Protokolle noch eine Erklärung „ohne besondere Vorkommnisse“.
Historische abgeschlossene Slots ohne Protokoll blockieren daher den regulären
Tagesabschluss nicht; spätere Ergänzungen benötigen einen eigenen auditierbaren
Importpfad.

Migration `018_add_exam_results.sql` führt die versionierten Bewertungsmodelle, die Bindung an eine Prüfungsrunde und das getrennte Ergebnisaggregat ein.
Für abgeschlossene historische Slots entsteht nur ein expliziter Marker, dass in lzug keine Ergebnisdaten vorliegen.
Die Migration erfindet weder Modellbindung noch Bewertung, Punkte, Berechnung, Beschluss oder Mitteilung.
Details zu Sichtbarkeit, Vier-Augen-Prinzip, Korrektur und Aufbewahrung beschreibt der [Ergebnisvertrag](architecture/exam-results.md).

Migration `019_add_exam_day_closures.sql` ergänzt Tagesrevision und formellen Abschlussstatus sowie unveränderliche Abschluss-, Wiederöffnungs-, Aufgaben-, Audit- und Exporthistorien.
Bereits abgeschlossene oder abgesagte Tage werden ausschließlich als historisch gesperrt gekennzeichnet.
Die Migration erzeugt dafür weder Akteur und Zeitpunkt noch eine vermeintlich erfüllte Prüfliste oder Begründung.
Offene, laufende und inkonsistente Bestände bleiben offen.
Den Sperr-, Korrektur- und Nachweisvertrag beschreibt der [formelle Tagesabschluss](architecture/exam-day-closure.md).

Migration `020_add_confirmed_plan_revisions.sql` ergänzt die unveränderliche Vorher-/Nachher-Historie bestätigter Planänderungen.
Migration `022_add_plan_consequences.sql` ergänzt deren getrennte, wiederholbare Benachrichtigungs- und Kalenderfolgen.
Vorhandene Nachrichten, Zustellungen und Kalenderidentitäten bleiben erhalten; vergangene Revisionen erzeugen bei der Migration keine neuen fachlichen Folgen.

Migration `023_add_exam_round_lifecycle.sql` verschiebt den fachlichen Abschluss vom gemeinsam genutzten Prüfungshalbjahr auf die ausschussbezogene Prüfungsrunde.
Sie ergänzt Rundenrevision, terminale Prüflingsstatus sowie unveränderliche Entscheidungs-, Wiederöffnungs-, Aufgaben-, Audit- und Exporthistorien.
Historische Halbjahres- und Rundenstände werden mit technischer Migrationsevidenz übernommen, ohne formale Abschlussnachweise zu erfinden.
Den Zustands-, Idempotenz- und Wiederanlaufvertrag beschreibt die [Folgenarchitektur](architecture/plan-change-consequences.md).
