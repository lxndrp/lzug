# Formeller Abschluss von Prüfungstagen

Der Tagesabschluss ist ein eigenes, revisionsgebundenes Aggregat für den gesamten Prüfungstag.
Vorsitz und Stellvertretung können einen Tag erst schließen, nachdem Durchführung, Anwesenheit, tatsächliche Besetzung, Ausfallvorgänge, Prüfungsprotokolle und Tagesbewertungen gemeinsam erneut geprüft wurden.
Ein vollständig und begründet abgesagter Tag benötigt keine erfundenen Anwesenheits-, Protokoll- oder Bewertungsdaten.

## Zustände und Voraussetzungen

`exam_day.closure_status` unterscheidet `open`, `closed`, `closed_exception`, `reopening` und `historical`.
Jede fachliche Änderung am offenen oder wieder geöffneten Tag erhöht `exam_day.revision`.
Abschluss und Wiederöffnung vergleichen die angegebene Revision unmittelbar vor dem Zustandswechsel und wirken mit ihren Voraussetzungen in derselben Datenbanktransaktion.

Der reguläre Abschluss verlangt ausschließlich endgültige Slotzustände, vollständige tatsächliche Daten und Besetzung, beendete Ausfallvorgänge, abschließbare Protokolle sowie vollständige Tagesbewertungen.
Ein berechnungsbereites Gesamtergebnis muss festgestellt sein.
Noch nicht eingetroffene zulässige externe Ergebnisbestandteile bleiben als offener Folgevorgang sichtbar und blockieren den Tag nicht.

Der Ausnahmeabschluss ist ausschließlich für genau eine fehlende Reaktion auf eine unveränderte, vollständig vorgelegte Protokollrevision zulässig.
Grund und bisherige Klärungsversuche sind Pflichtangaben.
Die fehlende Person erhält eine dauerhafte Nachfassaufgabe und eine Benachrichtigung.
Sie darf später auf genau diese Revision bestätigen oder einen Vorbehalt erfassen; jede Inhaltsänderung bleibt gesperrt.

## Sperre und zielgerichtete Wiederöffnung

Geschlossene Tagesdaten werden an derselben gemeinsamen Guard-Grenze in Durchführung, Anwesenheit, Ausfallprozess, Protokoll und Ergebnis geprüft.
Lesen und Exportieren sowie nachgelagerte externe Ergebnis-, Feststellungs-, Mitteilungs- und IHK-Statusvorgänge bleiben möglich, ohne die Tagesrevision zu verändern.
Vergangene Kalenderereignisse werden weder beim Abschluss noch bei einer reinen Tatsachenkorrektur synchronisiert.

Eine Wiederöffnung benötigt aktuelle Revision, Anlass, Quelle, Begründung und mindestens ein konkretes Objekt im Korrekturumfang.
Vorher zeigt die Auswirkungsprüfung abhängige Protokolle, Ergebnisse, Feststellungen, Mitteilungen und betroffene Personen.
Der gespeicherte Umfang wird um diese Abhängigkeiten erweitert; alle anderen Tagesdaten bleiben gesperrt.
Neue Protokollrevisionen beziehungsweise Ergebnis-Korrekturvorgänge machen frühere Bestätigungen und Feststellungen nachvollziehbar unwirksam.
Persönliche Aufgaben und Benachrichtigungen werden nur für tatsächlich Betroffene erzeugt.

Nach der Bearbeitung des angeforderten Umfangs prüft der erneute Abschluss die vollständige Matrix erneut.
Frühere Abschlüsse, Wiederöffnungen, Korrektur-Audits, Aufgaben und Exporte bleiben erhalten.
Identische Befehle sind über ihren Fingerabdruck idempotent; abweichende oder veraltete Befehle liefern einen Konflikt.

## HTTP- und Exportvertrag

- `GET /api/confirmed-plan-days/{id}/closure` liefert Revision, Status, vollständige Prüfliste, Warnungen, Referenzen, Aufgaben, Berechtigungen und Historie.
- `POST /api/confirmed-plan-days/{id}/closure` schließt regulär oder mit der eng begrenzten Ausnahme und verlangt `confirmed: true`.
- `POST /api/confirmed-plan-days/{id}/reopening-impact` prüft den beantragten Umfang ohne Mutation.
- `POST /api/confirmed-plan-days/{id}/reopenings` öffnet den geprüften Umfang revisionsgebunden.
- `GET /api/confirmed-plan-days/{id}/closure/export.json` und `.txt` erzeugen maschinen- beziehungsweise menschenlesbare Nachweise und protokollieren den Export ohne Änderung der Tagesrevision.

Tagesbezogene Schreiboperationen übertragen `day_revision`; Ergebnisvorgänge mit mehreren betroffenen Tagen verwenden `day_revisions`.
Die FastAPI-Fehlerabbildung liefert fachliche Validierungsbefunde mit HTTP 422 und Revisions- oder Sperrkonflikte mit HTTP 409.

## Migration und Demo

Migration `019_add_exam_day_closures.sql` kennzeichnet bereits abgeschlossene oder abgesagte Tage als `historical`.
Sie erfindet keinen Abschlussakteur, Zeitpunkt, Prüfstand oder Grund.
Offene, laufende und inkonsistente Bestände bleiben offen und müssen den vollständigen Vertrag erfüllen.
Auch ein historischer Tag kann nur über eine begründete zielgerichtete Wiederöffnung korrigiert werden.

Die Demo ergänzt reproduzierbare synthetische Tage für einen regulär abschließbaren vollständig abgesagten Tag und einen Ausnahmeabschluss mit genau einer fehlenden Protokollreaktion.
Die übrigen offenen beziehungsweise laufenden Zustände liefern negative Voraussetzungen.
Capability und Allowlist trennen Lesen, Export, Abschluss, Auswirkungsprüfung und Wiederöffnung; der bestehende Reset stellt den Seedzustand vollständig wieder her.
