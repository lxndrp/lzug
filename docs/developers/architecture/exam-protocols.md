# Versionierte Prüfungsprotokolle

Das Prüfungsprotokoll ist ein gemeinsamer, nachvollziehbarer Tatsachenstand
für genau einen tatsächlich gestarteten Prüfungsslot. Es entsteht atomar mit
dem Start und hält die zu diesem Zeitpunkt tatsächlich beteiligten Prüfer als
unveränderlichen Beteiligten-Snapshot fest. Ein Ausfall oder Nichterscheinen
vor dem Start erzeugt kein Protokoll; Unterbrechung und Abbruch nach dem Start
bleiben protokollpflichtig.

## Inhalt und Datenschutzgrenze

Jeder Inhaltsstand enthält die ausdrückliche Feststellung „ohne besondere
Vorkommnisse“ oder „mit besonderen Vorkommnissen“. Nur der zweite Fall enthält
strukturierte Einträge mit Kategorie, überprüfbarem Sachverhalt, Zeitpunkt und
erfassender Person. Zulässige Kategorien decken verspäteten Beginn,
Unterbrechung, Abbruch, abweichende Besetzung, Verfahrensabweichung,
Einwand/Vorbehalt und Sonstiges ab.

Freie Bewertungsbegründungen, Diagnosen und medizinische Angaben gehören nicht in dieses Aggregat.
Die UI weist vor der Erfassung auf diese Grenze hin.
Das Protokoll referenziert Prüfling, Termin, Ort, Anwesenheit und Beteiligte aus den zuständigen Aggregaten.
Es verweist auf den gesonderten [Ergebnisvorgang](exam-results.md), kopiert aber keine Bewertungen oder Begründungen in den Protokollinhalt.

## Versionen, Reaktionen und Korrektur

Ein Inhaltsupdate erzeugt immer eine neue unveränderliche Version. Nach der
Vorlage reagieren alle tatsächlich Beteiligten auf genau diese Version mit
Bestätigung oder einem protokollbezogenen Vorbehalt. Sobald ein neuer Stand
entsteht, bleiben alte Reaktionen in der Historie sichtbar, sind für den
aktuellen Abschluss aber überholt. Der reguläre Tagesabschluss akzeptiert nur
„vollständig bestätigt“ oder „vollständig mit Vorbehalt“.

Nach vollständiger Reaktion ist eine direkte Inhaltsänderung gesperrt. Ein
Beteiligter meldet zunächst begründeten Ergänzungsbedarf; Vorsitz oder
Stellvertretung öffnen daraus den Korrekturvorgang.
Nach einem bereits abgeschlossenen Prüfungstag ist zusätzlich der zulässige
[Wiederöffnungsnachweis des Tagesabschlusses](exam-day-closure.md) erforderlich.
Der neue Stand wird erneut vorgelegt und von allen Beteiligten behandelt.

## Zugriff, Aufbewahrung und Export

Inhalte lesen, bearbeiten und behandeln dürfen nur tatsächlich Beteiligte.
Vorsitz und Stellvertretung des Ausschusses dürfen lesen, Korrekturvorgänge
koordinieren und eine geöffnete Korrektur organisatorisch bearbeiten; ohne
eigene Teilnahme dürfen sie nicht bestätigen. Betreiberkonten erhalten keinen
fachlichen Zugriff.

Aufbewahrungsfrist und Rechtsgrundlage werden je lokaler Instanz konfiguriert;
das Produkt setzt keine willkürliche Standardfrist. Eine verbindliche Frist
kann nicht verkürzt werden. Rechtliche Aufbewahrungssperren und deren
begründete Freigabe bleiben nachvollziehbar. Menschenlesbarer und
maschinenlesbarer Export kennzeichnen unvollständige Stände; der
Maschinenexport enthält die vollständige Versions- und Reaktionshistorie.
