# Authentifizierung und Sitzungen

Die Authentifizierungsgrundlage trennt die technische Identität eines Kontos
von fachlichen Ausschussrollen. Ein `user_account` kann optional mit einer
`person` verknüpft sein und separat `is_operator` tragen. Betreiberrechte
erzeugen keine Ausschussmitgliedschaft und damit keine fachlichen Rechte.
Kennwort, TOTP, Passkeys und OIDC
folgen in #266–#268.

## Sessionregeln

`backend.auth.AuthenticationRepository` ist die interne, testbare Grenze für
Konten- und Sessionpflege. Es gibt in dieser Stufe keinen Netzwerk-Endpunkt zur
Kontenpflege und keinen Login-Endpunkt. Spätere Anmeldeverfahren erzeugen eine
Session ausschließlich über diesen Service beziehungsweise eine darauf
aufbauende Fachschicht für die Betreiber-CLI.

Die Konten-, Einladungs-, Sperr- und Recovery-Grundlage für diese Fachschicht
liegt in `backend.admin_service`. Die portable Go-Grenze und ihr
JSON-/Exit-Code-Vertrag sind in der [Betreiber-CLI-Referenz](operator-auth-cli.md)
beschrieben. Der Betreiber bleibt ohne `person_id`; eine Betreiberoperation
verleiht daher niemals eine Ausschussrolle.

Eine Session besteht aus zufälligem opaque Bearer-Material und einem separaten
CSRF-Token. In `auth_session` liegen nur SHA-256-Prüfwerte, nie die Token. Die
Session ist standardmäßig acht Stunden absolut gültig. Eine Rotation widerruft
die alte Session atomar und erzeugt eine neue; Logout, Kontensperrung und
expliziter Widerruf machen aktive Sessions sofort ungültig. Abgelaufene,
widerrufene oder inaktive Konten werden identisch als nicht authentifiziert
behandelt.

Das Session-Cookie heißt `__Host-lzug_session` und wird mit `Path=/`,
`HttpOnly`, `Secure` und `SameSite=Strict` ausgegeben. Es besitzt kein
`Domain`-Attribut. Der CSRF-Cookie `lzug_csrf` ist nicht `HttpOnly`, hat aber
dieselben `Secure`-/`SameSite`-/`Path`-Eigenschaften. Jede zustandsändernde
Fachoperation benötigt zusätzlich `X-CSRF-Token`; fehlende oder falsche Werte
liefern HTTP 403. GET-Fachoperationen benötigen kein CSRF-Token.

## HTTP-Grenze

`/api/health`, `/api`, `/api/openapi.json` und `/api/docs` sind bewusst öffentlich.
Health enthält ausschließlich Readiness-Status und Links, niemals Fachdaten.
Alle anderen Fachoperationen benötigen eine gültige Session. HTTP 401 bedeutet
fehlende, ungültige, abgelaufene oder widerrufene Authentifizierung. HTTP 403
ist für eine gültige Session ohne zulässigen Fach-Actor sowie CSRF- und spätere
Rollenfehler reserviert.

Der Actor wird ausschließlich aus der validierten Session, ihrem Konto und der
verknüpften Person aufgelöst. `created_by_member_id` und
`updated_by_member_id` aus JSON werden nicht als Identitätsbeweis akzeptiert;
der Server ersetzt sie durch die passende aktive Mitgliedschaft der
angemeldeten Person. Ein Request kann damit weder eine fremde Identität noch
Betreiberrechte in fachliche Rollen umwandeln.

## Ausschuss-Scope und Rollenrechte

`backend.authorization.AuthorizationService` erstellt für jede gültige
Session einen Scope ausschließlich aus aktiven Mitgliedschaften. Listen,
Details, Suche und aggregierte Planungsansichten werden auf diese Ausschüsse
begrenzt; indirekt verbundene Kandidaten-, Planungs-, Termin- und
Rückmeldungsdaten verwenden denselben Scope. Ein fremder Detailzugriff wird
ohne fremde Daten beantwortet.

Stamm- und Planungsdaten dürfen nur Vorsitz und Stellvertretung der aktiven
Mitgliedschaft verändern. Beide Rollen verwenden dieselbe Managementprüfung;
`ordinary` und `deputy` verändern diese Fachrechte nicht. Reguläre Mitglieder
dürfen ausschließlich ihre eigenen Verfügbarkeitsrückmeldungen und ihnen
zugeordnete spätere Aufgaben ändern. Inaktive oder historisch beendete
Mitgliedschaften werden weder als Actor noch als fachlicher Scope akzeptiert.

Die Angular-Oberfläche übermittelt keine Auswahl für den dokumentierten Actor.
Sie zeigt weiterhin fachliche Zielobjekte und Rückmeldungen, während die
serverseitige Prüfung die Sicherheitsgrenze bildet. OpenAPI beschreibt für
alle geschützten Fachoperationen die Session-/CSRF-Sicherheit sowie 401 und
403.

Angular nutzt die Standard-XSRF-Unterstützung von `HttpClient` mit den
kanonischen Cookie-/Headernamen. Der E2E-Server stellt Sessions ausschließlich
für den isolierten Playwright-Reset bereit; diese Route existiert nicht im
Produktionsserver.
