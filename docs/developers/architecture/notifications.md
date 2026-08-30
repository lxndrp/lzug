# Kanalneutrale Benachrichtigungen

Der fachliche Hinweis wird zuerst dauerhaft in `notification` gespeichert.
Web Push, der optionale E-Mail-Fallback und der Test-/Demo-Sink sind davon getrennte technische Zustellungen in `notification_delivery`.
Ein fehlender oder fehlerhafter Kanal entfernt den Hinweis deshalb nicht aus lzug und rollt den auslösenden Fachvorgang nicht zurück.

## Ereignisse und Idempotenz

Der Erstumfang erzeugt Hinweise für Verfügbarkeitsanfrage, Erinnerung, Fristüberschreitung und Planbestätigung.
Der eindeutige Schlüssel aus Empfänger, Ereignistyp und `origin_key` verhindert Duplikate bei erneutem Verarbeiten.
Erinnerungen gehen nur an Mitglieder mit mindestens einer offenen Rückmeldung; bei Fristüberschreitung kommen Vorsitz und Stellvertretung hinzu.
Planbestätigungen verwenden ausschließlich die tatsächlich bestätigten Prüfer- und Fallback-Zuordnungen.

`lzug-admin process-notifications` verarbeitet fällige Erinnerungs- und Fristereignisse, technische Zustellwiederholungen sowie fällige Folgen bestätigter Planänderungen.
Pro Lauf werden höchstens 20 fällige Zustellungen verarbeitet.
Jeder einzelne Auftrag wird atomar mit einem zufälligen Claim-Token für zwei Minuten beansprucht, bevor der nächste Auftrag des begrenzten Laufs ausgewählt wird.
Auswahl und Claim erfolgen gemeinsam in einer kurzen SQLite-Schreibtransaktion; die dafür benötigten, datensparsamen Kanalparameter werden noch in dieser Transaktion gelesen.
Web Push, SMTP und Sink werden erst nach deren Commit aufgerufen.
Das Ergebnis wird anschließend in einer neuen kurzen Transaktion nur gespeichert, wenn Token und Ablauf des Claims weiterhin gültig sind.

Ein paralleler Worker überspringt aktive Claims.
Nach Ablauf darf er den Auftrag reproduzierbar übernehmen.
Ein verspäteter erster Worker kann den neuen Zustand nicht überschreiben.
Vorübergehende Fehler werden mit begrenztem exponentiellem Abstand höchstens viermal versucht.
Endgültig ungültige Push-Endpunkte werden nur zusammen mit dem weiterhin gültigen Abschluss-Claim deaktiviert.
Eine ausbleibende technische Service-Worker-Bestätigung ist kein Lesestatus; sie kann bei konfiguriertem SMTP den E-Mail-Fallback auslösen.

## Zustellgarantie und Absturzgrenze

Der Claim verhindert ausschließlich die gleichzeitige Verarbeitung desselben internen Auftrags.
Er kann keine Exactly-once-Zustellung bei einem externen System garantieren: Akzeptiert ein externes System die Nachricht und der Worker fällt vor dem Ergebnis-Commit aus, wird der abgelaufene Auftrag erneut beansprucht. lzug behält dabei genau einen internen Auftrag und verwirft Ergebnisse älterer Claims, extern kann die Wiederholung jedoch sichtbar sein.

- **Web Push:** Eine mehrdeutige HTTP-Antwort oder ein Absturz nach Annahme
kann einen weiteren Push erzeugen.
Der stabile Topic-Wert erleichtert dem Push-Dienst die Zusammenfassung, ist aber keine Exactly-once-Garantie.
- **E-Mail:** Nach Annahme durch das SMTP-Relay und vor dem Ergebnis-Commit kann
eine Wiederholung zu zwei E-Mails führen.
Das Relay stellt keine transaktionale Bestätigung gegenüber SQLite bereit.
- **Sink:** Der Sink kontaktiert keinen realen Empfänger und speichert keine
zweite Nachricht.
Ein wiederholter Sink-Aufruf bleibt deshalb ohne externe Nebenwirkung; der interne Zustellzustand unterliegt dennoch demselben Claim-Vertrag.

## Kanäle und Datenminimierung

Web Push verwendet einen persistenten P-256-VAPID-Schlüssel aus `LZUG_WEB_PUSH_VAPID_PRIVATE_KEY` und den Kontakt in `LZUG_WEB_PUSH_SUBJECT`.
Der Push selbst enthält keine Fachdaten.
Er weckt den Service Worker, der eine generische Vorschau zeigt und auf die authentifizierte Benachrichtigungsansicht verweist.

SMTP wird nur aktiviert, wenn `LZUG_SMTP_HOST` gesetzt ist.
Ohne Relay entstehen keine unerfüllbaren E-Mail-Aufträge.
Ziel-URL, Absender, STARTTLS und optionale Zugangsdaten werden über die `LZUG_EXTERNAL_URL`- und `LZUG_SMTP_*`-Variablen konfiguriert.
Die Anwendung startet ohne diese Werte.

Test- und Demo-Instanzen setzen `LZUG_NOTIFICATION_SINK=operator`.
Dann wird jede technische Zustellung ausschließlich als bestätigter Sink-Versuch protokolliert; vorgesehene Empfänger werden nicht kontaktiert.
Ein gezielter synthetischer Kanaltest ohne echte Fachdaten ist mit `lzug-admin test-notification --member-id <id> --channel web_push|email` möglich.

## Einsicht und Diagnose

`GET /api/notifications` liefert ausschließlich eigene Inhalte.
Vorsitz und Stellvertretung erhalten über `GET /api/notification-overview` die erzeugten Zustellungen und über `GET /api/notification-problems` deren problematische Teilmenge, jeweils nur als technische Metadaten ihres Ausschusses; die Inhalte anderer Empfänger fehlen bewusst.
Betreiber-Kommandos geben ebenfalls nur Status, Versuchszahl und Diagnosecode aus.
Die technische Übersicht ergänzt ohne Nachrichteninhalt den Claim-Zustand `idle`, `active` oder `expired` sowie Claim- und Ablaufzeitpunkt; der schreibberechtigende Claim-Token wird nicht ausgegeben.
Betreiberrechte erzeugen keine fachlichen Ausschussrechte.

Die fachliche Ableitung zusammengefasster Hinweise aus bestätigten Planrevisionen und das Überholen noch unversuchter Zwischenstände beschreibt der [Planänderungs-Folgenvertrag](plan-change-consequences.md).
