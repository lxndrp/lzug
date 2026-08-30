# Fachliches Datenmodell

Dieses Dokument beschreibt die fachlichen Begriffe, Aggregate, Beziehungen und Invarianten von lzug.
Es ist keine zweite API-, Feld- oder Schemareferenz.
Die ausführbare technische Struktur liegt in den SQLAlchemy-Modellen, `db/schema.sql` und den Migrationen; die öffentliche HTTP-Schnittstelle in der OpenAPI-Quelle.

## Aggregate und Beziehungen

```mermaid
erDiagram
  COMMITTEE ||--o{ MEMBERSHIP : has
  PERSON ||--o{ MEMBERSHIP : holds
  COMMITTEE ||--o{ EXAM_ROUND : plans
  EXAM_HALF_YEAR ||--o{ EXAM_ROUND : groups
  EXAM_ROUND ||--o{ CONFIRMED_PLAN_REVISION : revises
  EXAM_ROUND ||--o{ ROUND_CANDIDATE : includes
  EXAM_ROUND ||--o{ EXAM_DAY : contains
  EXAM_DAY ||--o{ EXAM_SLOT : schedules
  EXAM_DAY ||--o{ EXAM_DAY_CLOSURE : closes
  EXAM_DAY ||--o{ EXAM_DAY_REOPENING : corrects
  EXAM_SLOT ||--o| EXAM_PROTOCOL : documents
  EXAM_PROTOCOL ||--|{ EXAM_PROTOCOL_REVISION : versions
  EXAM_PROTOCOL_REVISION ||--o{ EXAM_PROTOCOL_ENTRY : records
  EXAM_PROTOCOL_REVISION ||--o{ EXAM_PROTOCOL_RESPONSE : confirms
  EXAM_ROUND ||--o| ASSESSMENT_MODEL_BINDING : binds
  ASSESSMENT_MODEL_VERSION ||--o{ ASSESSMENT_MODEL_BINDING : selected_by
  ROUND_CANDIDATE ||--o| EXAM_RESULT : receives
  EXAM_RESULT ||--o{ INDIVIDUAL_ASSESSMENT : collects
  EXAM_RESULT ||--o{ RESULT_DETERMINATION : versions
  EXAM_DAY ||--o{ EXAM_DAY_ASSIGNMENT : staffs
  MEMBERSHIP ||--o{ EXAM_DAY_ASSIGNMENT : fulfils
  EXAM_ROUND ||--o{ NOTIFICATION : causes
  EXAM_SLOT ||--o{ CALENDAR_EVENT : informs
  EXAM_DAY_ASSIGNMENT ||--o{ ABSENCE_REPORT : affects
```

- **Ausschuss und Person**: Ein Ausschuss ist der fachliche und
autorisierende Arbeitskontext.
Personen können Mitgliedschaften mit Rolle, Vertreterseite und Aktivitätsstatus halten.
Ein Betreiberkonto ist keine fachliche Mitgliedschaft.
- **Prüfungszeitraum und Prüfungsrunde**: Ein Prüfungshalbjahr fasst die
zeitliche Einordnung; eine Prüfungsrunde ist der planbare Vorgang eines Ausschusses.
Zugeordnete Prüflinge gehören zur Runde, nicht unmittelbar zum Ausschuss.
- **Planung und Durchführung**: Orte, Verfügbarkeiten, mögliche Tage und ein
Vorschlag führen zu Prüfungstagen, Slots und Besetzungen.
Die bestätigte Planung ist die Grundlage für Benachrichtigungen, Kalender und Ausfälle.
Eine begründete Änderung vor dem tatsächlichen Start behält die Objektidentitäten bei
und schreibt Vorher- und Nachher-Zustand als unveränderliche Planrevision.
- **Kommunikation und Dokumente**: Ein fachlicher Hinweis ist von seinen
technischen Zustellungen getrennt.
Persönliche Kalender enthalten nur die eigene Einplanung.
Dokumente besitzen fachliche Metadaten; ihr Inhalt bleibt in einer separaten, kontrollierten Ablage.
- **Ausfall und Ersatz**: Eine Ausfallmeldung bezieht sich auf eine bestätigte
  Besetzung. Rückmeldungen, Ersatzwahl und Korrekturen bilden einen
  nachvollziehbaren Prozess, der den bestätigten Plan nicht voreilig ändert.
- **Prüfungsprotokoll**: Jeder tatsächlich gestartete Slot besitzt genau ein
  gemeinsames Protokoll. Es stellt den regulären Verlauf ausdrücklich fest oder
  erfasst Besonderheiten strukturiert. Inhalt, Reaktionen und Korrekturen sind
  versioniert; Bewertungsdaten bleiben dem getrennten Bewertungsaggregat
  vorbehalten.
- **Bewertungsmodell und Ergebnis**: Eine Runde wird vor der ersten Bewertung an eine unveränderliche, gültige Modellversion gebunden.
  Der Ergebnisvorgang sammelt verdeckte und später kontrolliert offengelegte Einzelbewertungen, gemeinsame Komponentenbeschlüsse, vieräugig bestätigte Eingangsergebnisse, reproduzierbare Berechnungen sowie versionierte Feststellungen, Bestätigungen, Mitteilungen, Korrekturen und Exporte.
- **Tagesabschluss**: Ein formeller Abschluss bindet den vollständigen Prüfungs-, Protokoll- und Bewertungsstand eines ganzen Tages an dessen Revision.
  Nachträgliche Änderungen benötigen eine begründete zielgerichtete Wiederöffnung und erhalten frühere Abschluss- und Korrekturstände.

## Fachliche Invarianten

- Planung und Fachzugriffe bleiben im Ausschusskontext; Betreiberrechte
ersetzen keine Ausschussrolle.
- Vorsitz und Stellvertretung sind in der fachlichen Bearbeitung gleichgestellt;
die Stellvertretung bezeichnet nur die Vertretungsfunktion.
- Eine bestätigte Tagesbesetzung deckt Arbeitgeber-, Arbeitnehmer- und
Schulseite ab und verfügt zusätzlich über einen Fallback.
Ein Tag besteht nicht ausschließlich aus mündlichen Ergänzungsprüfungen.
- Bestätigte Pläne dürfen nur vor dem tatsächlichen Start und ausschließlich
als vollständiges, revisionsgebundenes Aggregat geändert werden.
Jede Revision verlangt einen Grund und einen berechtigten Akteur; veraltete
Revisionsstände oder gesperrte Tage verändern weder Plan noch Historie.
- Verfügbarkeiten, Ersatz und Kalenderereignisse beziehen sich auf die
konkrete Runde und den betroffenen Tagesabschnitt.
Ein Ersatz wird erst nach kontrollierter Auswahl wirksam.
- Fachliche Hinweise bleiben erhalten, wenn eine externe Zustellung scheitert.
  Wiederholungen dürfen keinen zweiten gleichartigen Hinweis erzeugen.
- Vor dem tatsächlichen Start entsteht kein Protokoll. Nach dem Start bleiben
  auch unterbrochene oder abgebrochene Prüfungen protokollpflichtig. Eine neue
  Inhaltsversion macht Reaktionen auf den vorigen Stand sichtbar überholt;
  regulär abschließbar ist nur ein von allen tatsächlich Beteiligten
  behandelter aktueller Stand.
- Nur tatsächlich beteiligte Prüfer dürfen inhaltlich reagieren. Vorsitz und
  Stellvertretung dürfen ausschussbezogen lesen sowie begründete
  Korrekturvorgänge koordinieren; Betreiberrechte gewähren keinen
  Protokollzugriff.
- Individuelle Bewertungen sind bis zur vollständigen Eigenbewertung und einem kontrollierten Offenlegungsschritt für andere Beteiligte unsichtbar.
  Ein externes Eingangsergebnis wirkt erst nach unabhängiger Bestätigung; ein berechneter Vorschlag wird erst durch einen ordnungsgemäß besetzten Beschluss zum festgestellten Ergebnis.
  Korrekturen überschreiben keinen früheren Stand.
- Ein geschlossener Prüfungstag sperrt Durchführung, Anwesenheit, Besetzung, Ausfallentscheidungen, Protokollinhalt und Tagesbewertungen gemeinsam.
  Nur der ausdrücklich wieder geöffnete Umfang ist revisionsgebunden korrigierbar; zulässige nachgelagerte externe Ergebnisvorgänge verändern den Tagesstand nicht.
- Personenbezogene Inhalte sind auf erforderliche Beteiligte begrenzt:
Kalenderfeeds offenbaren keine Prüflings- oder Fremdbesetzungsdaten; Dokumentpfade und Zustellungsdetails sind keine frei wählbaren Fachdaten.

Ändert sich eine fachliche Regel, wird dieses Dokument gemeinsam mit den zugehörigen Services und Tests geprüft.
Ändert sich nur eine technische Darstellung, bleibt deren ausführbare Quelle maßgeblich.
