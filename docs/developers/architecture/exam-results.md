# Regelgebundene Bewertungen und Ergebnisse

Der Ergebnisvorgang ist das getrennte Bewertungsaggregat eines Prüflings in einer Prüfungsrunde.
Vor dem ersten Bewertungsinput bindet Vorsitz oder Stellvertretung die Runde an genau eine unveränderliche Bewertungsmodellversion.
Sie enthält IHK, Beruf und gegebenenfalls Schwerpunkt, Rechts- und Richtlinienreferenzen, Gültigkeit, Rohpunkteskalen, Gewichte, Rundung, Notenzuordnung, Bestehensregeln, Beschlussquorum und Aufbewahrungsregel.
Nach dem ersten Input ist ein Modellwechsel gesperrt.

## Bewertung und Sichtbarkeit

Das gebundene Modell trennt Dokumentation, Präsentation, Fachgespräch und externe Prüfungsbereiche.
Kriterien können eigene Rohpunkteskalen verwenden; die Anwendung normalisiert sie nachvollziehbar auf 0 bis 100 Punkte.
Gewichte werden auf jeder Ebene als exakte Dezimalwerte geprüft und müssen 100 Prozent ergeben.

Eigene Kriterienbewertungen entstehen zunächst als verdeckte, versionierte Entwürfe oder Abgaben.
Andere Beteiligte sehen nur aggregierte Vollständigkeitszahlen.
Eine Offenlegung ist ein eigener kontrollierter Schritt und setzt die vollständigen vorgeschriebenen Eigenbewertungen voraus.
Gemeinsame Komponenten erhalten danach einen dokumentierten Beschluss; unabhängige Komponenten verwenden die vorgeschriebene Anzahl vollständiger Bewertungen.
Überschreitet deren Spannweite die Modellgrenze, wird eine zusätzliche vollständige Bewertung benötigt.

Externe Eingangsergebnisse speichern Punkte, optional die Note, fachlichen Status, feststellende Stelle und maßgebliche Bezugsquelle.
Sie fließen erst nach der Bestätigung durch ein anderes berechtigtes Mitglied ein.
Erfassung und Bestätigung durch dieselbe Person sind technisch ausgeschlossen.

## Berechnung, Feststellung und Mitteilung

Sobald alle erforderlichen Komponenten und bestätigten Eingangsergebnisse vorliegen, erzeugt der Service einen reproduzierbaren Berechnungsstand.
Sein Fingerabdruck bindet Modellversion, Inputrevisionen und unrundes Ergebnis.
Der Berechnungsweg hält Einzelwerte, Gewichte, Zwischenstand, Rundung und Grundlage der Bestehensgrenzen fest.
Dieser Stand ist ein Vorschlag und noch keine Ergebnisfeststellung.

Die Feststellung ist ein eigener Ausschussbeschluss mit den tatsächlich Mitwirkenden, Quorum, Stimmen und optionalen abweichenden Voten.
Anschließend bestätigt jedes beteiligte Mitglied die sachliche Richtigkeit der Ergebnisniederschrift.
Erst nach allen Bestätigungen kann die verantwortliche Person Art und Zeitpunkt der Ergebnismitteilung sowie den Status eines externen IHK-Dokuments dokumentieren.
Berechnungsbereitschaft, Feststellung und Mitteilung bleiben damit drei getrennte Zustände.

## Korrektur, Tagesabschluss und Aufbewahrung

Ein festgestellter Stand ist unveränderlich.
Vorsitz oder Stellvertretung öffnet einen begründeten Korrekturvorgang; nach abgeschlossenem Prüfungstag ist zusätzlich eine zulässige [Wiederöffnungsreferenz des Tagesabschlusses](exam-day-closure.md) nötig.
Korrigierte Inputs erzeugen neue Revisionen und eine Neufeststellung.
Die vorherige Feststellung, Mitteilung und darauf beruhende Exporte bleiben in der Historie sichtbar und werden als überholt beziehungsweise ersetzt markiert.

`GET /api/confirmed-plan-days/{day_id}/result-completion` liefert dem Tagesabschlussvertrag die bewertungsbezogene Vollständigkeit.
Tagesbezogene Bewertungen müssen vollständig sein; ein berechnungsbereites, aber noch nicht festgestelltes Ergebnis sowie ein offener Korrekturvorgang verhindern den regulären Abschluss.

Die gebundene Modellversion liefert Rechtsgrundlage und Mindestdauer der Aufbewahrung.
Eine gesetzte Frist darf weder unter diese Mindestdauer noch unter einen bereits verbindlichen Wert verkürzt werden.
Rechtliche Sperren und ihre begründete Freigabe bleiben nachvollziehbar.

## Export, Zugriff und Bestandsmigration

Maschinen- und menschenlesbare Exporte kennzeichnen Entwurf oder festgestellten Stand und sind keine amtlichen IHK-Dokumente.
Der Maschinenexport enthält Modell, Ergebnis, Berechnungsweg und vollständige Feststellungs-, Korrektur-, Mitteilungs- und Exporthistorie.
Der Protokollexport referenziert denselben Ergebnisvorgang, ohne Bewertungsbegründungen in das Verlaufsprotokoll zu kopieren.

Nur tatsächlich Beteiligte und ausschussbezogen verantwortliche Vorsitzende oder Stellvertretungen erhalten Fachzugriff.
Eigene Bewertungen und Niederschriftsbestätigungen bleiben an die persönliche Beteiligung gebunden; Betreiberkonten erhalten keinen Ergebniszugriff.

Migration `018_add_exam_results.sql` erfindet keine historischen Modelle, Bewertungen, Punkte, Beschlüsse oder Mitteilungen.
Für bereits abgeschlossene Slots wird ausschließlich der explizite Marker `no_result_data_in_lzug` angelegt.
Geplante und laufende Vorgänge bleiben bis zur bewussten Modellbindung unverändert.
