# Ausfall- und Ersatzprozess

Der Ausfallprozess arbeitet ausschließlich auf bestätigten Prüfungstagen und konkreten Besetzungen.
Eine Ausfallmeldung ändert den bestätigten Plan nicht sofort und sagt weder Slots noch Prüfungstage automatisch ab.

## Zuständigkeit und Zustände

Ein Mitglied meldet nur den eigenen Ausfall.
Vorsitz und Stellvertretung dürfen Ausfälle im eigenen Ausschuss erfassen, Ersatz auswählen, betroffene Slots mit Begründung absagen und einen bereits entschiedenen Prozess mit Begründung wieder öffnen.
Prüflingsausfälle bleiben im Durchführungsstatus.

Die Zustände sind `reported`, `fallback_requested`, `fallback_confirmed`, `fallback_expired`, `replacement_requested`, `replacement_selected`, `resolved`, `withdrawn`, `no_replacement_available` und `exam_day_cancelled`.
Antworten werden als `pending`, `available` oder `unavailable` gespeichert.
Jede Zustandsänderung erzeugt ein unveränderliches `absence_audit_event`; `version` schützt Ersatzentscheidungen vor veralteten Bearbeitungsständen.

## Ersatzlogik

Mindestens 48 Stunden vor Beginn erhält ein geeigneter Fallback exklusiv bis zu 24 Stunden Zeit.
Bei dringenden Meldungen werden Fallback und weitere geeignete Mitglieder parallel angefragt.
Geeignet bedeutet aktiv, für den Tagesabschnitt verfügbar, im Prüfungshalbjahr konfliktfrei und für den Ersatz eines regulären Prüfers auf derselben Vertreterseite.
Eine Auswahl ist genau einmal pro Versionsstand möglich.

Ein regulärer Ersatz erzeugt Kalender-Gegenaufträge für die alte und neue Besetzung.
Der Ersatz eines Fallbacks ändert nur diese Fallback-Einplanung.
Absagen erzeugen ausschließlich Stornierungsaufträge für den betroffenen Tagesabschnitt.
Die technische Verarbeitung erfolgt später über den gemeinsamen Kalendervertrag.

## API-Grenze

- `POST /api/absence-reports` meldet einen Ausfall.
- `GET /api/absence-reports` und `GET /api/absence-reports/{id}` liefern den
zugänglichen Prozess einschließlich Antworten und Audit-Historie.
- `PATCH /api/replacement-responses/{id}` beantwortet eine eigene Anfrage.
- `POST /api/absence-reports/{id}/select-replacement` wählt kontrolliert einen
verfügbaren Ersatz.
- `POST /api/absence-reports/{id}/withdraw`, `/reopen` und `/cancel` führen die
entsprechend autorisierten Korrekturen aus.

Benachrichtigungen werden über den kanalneutralen Vertrag gespeichert.
Bei dringlichen Meldungen werden Web Push und ein konfiguriertes E-Mail-Relay unabhängig voneinander angestoßen.
Ohne E-Mail-Konfiguration bleibt der Prozess nutzbar und die fehlende externe Zustellung wird als technische Nichtverfügbarkeit sichtbar.
