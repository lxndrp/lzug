# Kanalneutrale Benachrichtigungen

Der fachliche Hinweis wird zuerst dauerhaft in `notification` gespeichert.
Web Push, der optionale E-Mail-Fallback und der Test-/Demo-Sink sind davon
getrennte technische Zustellungen in `notification_delivery`. Ein fehlender
oder fehlerhafter Kanal entfernt den Hinweis deshalb nicht aus lzug und rollt
den auslösenden Fachvorgang nicht zurück.

## Ereignisse und Idempotenz

Der Erstumfang erzeugt Hinweise für Verfügbarkeitsanfrage, Erinnerung,
Fristüberschreitung und Planbestätigung. Der eindeutige Schlüssel aus
Empfänger, Ereignistyp und `origin_key` verhindert Duplikate bei erneutem
Verarbeiten. Erinnerungen gehen nur an Mitglieder mit mindestens einer offenen
Rückmeldung; bei Fristüberschreitung kommen Vorsitz und Stellvertretung hinzu.
Planbestätigungen verwenden ausschließlich die tatsächlich bestätigten
Prüfer- und Fallback-Zuordnungen.

`lzug-admin process-notifications` verarbeitet fällige Erinnerungs- und
Fristereignisse sowie technische Wiederholungen. Vorübergehende Fehler werden
mit begrenztem exponentiellem Abstand höchstens viermal versucht. Endgültig
ungültige Push-Endpunkte werden deaktiviert. Eine ausbleibende technische
Service-Worker-Bestätigung ist kein Lesestatus; sie kann bei konfiguriertem
SMTP den E-Mail-Fallback auslösen.

## Kanäle und Datenminimierung

Web Push verwendet einen persistenten P-256-VAPID-Schlüssel aus
`LZUG_WEB_PUSH_VAPID_PRIVATE_KEY` und den Kontakt in
`LZUG_WEB_PUSH_SUBJECT`. Der Push selbst enthält keine Fachdaten. Er weckt den
Service Worker, der eine generische Vorschau zeigt und auf die authentifizierte
Benachrichtigungsansicht verweist.

SMTP wird nur aktiviert, wenn `LZUG_SMTP_HOST` gesetzt ist. Ohne Relay entstehen
keine unerfüllbaren E-Mail-Aufträge. Ziel-URL, Absender, STARTTLS und optionale
Zugangsdaten werden über die `LZUG_EXTERNAL_URL`- und `LZUG_SMTP_*`-Variablen
konfiguriert. Die Anwendung startet ohne diese Werte.

Test- und Demo-Instanzen setzen `LZUG_NOTIFICATION_SINK=operator`. Dann wird
jede technische Zustellung ausschließlich als bestätigter Sink-Versuch
protokolliert; vorgesehene Empfänger werden nicht kontaktiert. Ein gezielter
synthetischer Kanaltest ohne echte Fachdaten ist mit
`lzug-admin test-notification --member-id <id> --channel web_push|email`
möglich.

## Einsicht und Diagnose

`GET /api/notifications` liefert ausschließlich eigene Inhalte. Vorsitz und
Stellvertretung erhalten über `GET /api/notification-overview` die erzeugten
Zustellungen und über `GET /api/notification-problems` deren problematische
Teilmenge, jeweils nur als technische Metadaten ihres Ausschusses; die Inhalte
anderer Empfänger fehlen bewusst.
Betreiber-Kommandos geben ebenfalls nur Status, Versuchszahl und Diagnosecode
aus. Betreiberrechte erzeugen keine fachlichen Ausschussrechte.
