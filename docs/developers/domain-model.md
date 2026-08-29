# Fachliches Datenmodell

Dieses Dokument beschreibt die fachlichen Begriffe, Aggregate, Beziehungen und
Invarianten von lzug. Es ist keine zweite API-, Feld- oder Schemareferenz. Die
ausführbare technische Struktur liegt in den SQLAlchemy-Modellen,
`db/schema.sql` und den Migrationen; die öffentliche HTTP-Schnittstelle in der
OpenAPI-Quelle.

## Aggregate und Beziehungen

```mermaid
erDiagram
  COMMITTEE ||--o{ MEMBERSHIP : has
  PERSON ||--o{ MEMBERSHIP : holds
  COMMITTEE ||--o{ EXAM_ROUND : plans
  EXAM_HALF_YEAR ||--o{ EXAM_ROUND : groups
  EXAM_ROUND ||--o{ ROUND_CANDIDATE : includes
  EXAM_ROUND ||--o{ EXAM_DAY : contains
  EXAM_DAY ||--o{ EXAM_SLOT : schedules
  EXAM_DAY ||--o{ EXAM_DAY_ASSIGNMENT : staffs
  MEMBERSHIP ||--o{ EXAM_DAY_ASSIGNMENT : fulfils
  EXAM_ROUND ||--o{ NOTIFICATION : causes
  EXAM_SLOT ||--o{ CALENDAR_EVENT : informs
  EXAM_DAY_ASSIGNMENT ||--o{ ABSENCE_REPORT : affects
```

- **Ausschuss und Person**: Ein Ausschuss ist der fachliche und
  autorisierende Arbeitskontext. Personen können Mitgliedschaften mit Rolle,
  Vertreterseite und Aktivitätsstatus halten. Ein Betreiberkonto ist keine
  fachliche Mitgliedschaft.
- **Prüfungszeitraum und Prüfungsrunde**: Ein Prüfungshalbjahr fasst die
  zeitliche Einordnung; eine Prüfungsrunde ist der planbare Vorgang eines
  Ausschusses. Zugeordnete Prüflinge gehören zur Runde, nicht unmittelbar zum
  Ausschuss.
- **Planung und Durchführung**: Orte, Verfügbarkeiten, mögliche Tage und ein
  Vorschlag führen zu Prüfungstagen, Slots und Besetzungen. Die bestätigte
  Planung ist die Grundlage für Benachrichtigungen, Kalender und Ausfälle.
- **Kommunikation und Dokumente**: Ein fachlicher Hinweis ist von seinen
  technischen Zustellungen getrennt. Persönliche Kalender enthalten nur die
  eigene Einplanung. Dokumente besitzen fachliche Metadaten; ihr Inhalt bleibt
  in einer separaten, kontrollierten Ablage.
- **Ausfall und Ersatz**: Eine Ausfallmeldung bezieht sich auf eine bestätigte
  Besetzung. Rückmeldungen, Ersatzwahl und Korrekturen bilden einen
  nachvollziehbaren Prozess, der den bestätigten Plan nicht voreilig ändert.

## Fachliche Invarianten

- Planung und Fachzugriffe bleiben im Ausschusskontext; Betreiberrechte
  ersetzen keine Ausschussrolle.
- Vorsitz und Stellvertretung sind in der fachlichen Bearbeitung gleichgestellt;
  die Stellvertretung bezeichnet nur die Vertretungsfunktion.
- Eine bestätigte Tagesbesetzung deckt Arbeitgeber-, Arbeitnehmer- und
  Schulseite ab und verfügt zusätzlich über einen Fallback. Ein Tag besteht
  nicht ausschließlich aus mündlichen Ergänzungsprüfungen.
- Verfügbarkeiten, Ersatz und Kalenderereignisse beziehen sich auf die
  konkrete Runde und den betroffenen Tagesabschnitt. Ein Ersatz wird erst nach
  kontrollierter Auswahl wirksam.
- Fachliche Hinweise bleiben erhalten, wenn eine externe Zustellung scheitert.
  Wiederholungen dürfen keinen zweiten gleichartigen Hinweis erzeugen.
- Personenbezogene Inhalte sind auf erforderliche Beteiligte begrenzt:
  Kalenderfeeds offenbaren keine Prüflings- oder Fremdbesetzungsdaten;
  Dokumentpfade und Zustellungsdetails sind keine frei wählbaren Fachdaten.

Ändert sich eine fachliche Regel, wird dieses Dokument gemeinsam mit den
zugehörigen Services und Tests geprüft. Ändert sich nur eine technische
Darstellung, bleibt deren ausführbare Quelle maßgeblich.
