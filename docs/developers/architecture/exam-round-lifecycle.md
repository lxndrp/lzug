# Lebenszyklus einer Prüfungsrunde

Der fachliche Abschluss gehört zur Prüfungsrunde eines Ausschusses, nicht zum gemeinsam genutzten Prüfungshalbjahr.
Vorsitz und Stellvertretung besitzen dieselben Verwaltungsrechte; ein technischer Operator erhält daraus keinen fachlichen Zugriff.

## Zustände und Entscheidungen

Eine neu angelegte Runde ist `open` und trägt eine monoton steigende `revision`.
Der reguläre Abschluss setzt einen bestätigten oder begonnenen Plan, nachweislich geschlossene Prüfungstage, terminale Prüflingsstatus, abgeschlossene Ausfall- und Planfolgen sowie das Fehlen offener Korrekturen voraus.
Die API liefert die vollständige Matrix, damit die Oberfläche alle erfüllten und offenen Voraussetzungen gemeinsam darstellt.

Eine vollständige Absage ist nur zulässig, solange kein Prüfungsslot tatsächlich begonnen hat.
Alle aktiven Prüflinge müssen zuvor wirksam neu zugeordnet, verbindlich verschoben oder durch IHK-Entscheidung beendet worden sein.
Die Absage beendet zukünftige Tage und Slots, storniert künftige Kalenderereignisse und erzeugt Benachrichtigungen.

Abschluss und Absage benötigen die angezeigte Revision sowie eine ausdrückliche Bestätigung.
Identische Wiederholungen sind idempotent; eine abweichende oder veraltete Entscheidung führt zu `409 Conflict`.

## Sperre und gezielte Wiederöffnung

`closed`, `cancelled` und `historical` sperren alle rundenbezogenen Fachdaten zentral am HTTP-Rand.
Eine Wiederöffnung dokumentiert Anlass, Quelle, Begründung und einen begrenzten Korrekturbereich.
Die Auswirkungsanalyse erweitert einen Prüfungstag um abhängige Protokolle und Ergebnisse, ermittelt betroffene Ausschussmitglieder und kennzeichnet bereits von der IHK verarbeitete Ergebnisdokumente für Klärung.

Während `reopening` bleiben nicht freigegebene Daten gesperrt.
Nach der Korrektur entscheidet Vorsitz oder Stellvertretung erneut; der neue Nachweis verweist auf die abgelöste Entscheidung.
Offene Wiederöffnungsaufgaben werden dabei abgeschlossen.

## Historie und Export

`exam_round_decision`, `exam_round_reopening` und `exam_round_audit_event` bewahren Entscheidungen und ihre Reihenfolge.
Der Entscheidungssnapshot enthält Halbjahr, Ausschuss, Rollen, Prüflinge, Planrevisionen, Tage, Slots, Protokolle und Ergebnisstände.
JSON- und Textnachweise sind an die aktuelle Rundenrevision gebunden.
Eine Wiederöffnung kennzeichnet vorherige Exporte als überholt, ohne sie zu löschen.

## Migration und Demo

Migration `023_add_exam_round_lifecycle.sql` macht frühere globale Halbjahresabschlüsse zu administrativ archivierten Kontexten und hält den Altstatus als Migrationsevidenz fest.
Frühere abgeschlossene Runden werden `historical`, ohne Akteure, Prüflisten oder formale Abschlussentscheidungen zu erfinden.
Frühere Absagen bleiben Absagen; unbekannte Altzustände werden in der Migrationsevidenz als klärungsbedürftig markiert.

Die öffentliche Demo führt jeden Lese-, Export- und Mutationspfad mit eigener Capability und Allowlist-Regel.
Nur Vorsitz und Stellvertretung dürfen die Lebenszyklusmutationen ausführen; die synthetischen Daten bleiben flüchtig und werden beim Reset verworfen.

## Ausführbare Verträge

- Service und zentrale Sperre: `backend/exam_round_lifecycle.py`
- HTTP-Routen und Fehlerabbildung: `backend/fastapi_app.py`
- Persistenz: `backend/models.py` und `db/migrations/023_add_exam_round_lifecycle.sql`
- Demo-Policy: `demo/runtime_policy.py`
- Oberfläche: `frontend/src/app/exam-half-years/`
- Vertragsprüfungen: `backend/tests/test_exam_round_lifecycle.py`
