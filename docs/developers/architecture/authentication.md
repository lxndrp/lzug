# Authentifizierung und Sitzungen

Die Authentifizierungsgrundlage trennt die technische Identität eines Kontos
von fachlichen Ausschussrollen. Ein `user_account` kann optional mit einer
`person` verknüpft sein und separat `is_operator` tragen. Betreiberrechte
erzeugen keine Ausschussmitgliedschaft und damit keine fachlichen Rechte.
Die vollständige Rollenprüfung folgt in #265; Kennwort, TOTP, Passkeys und OIDC
folgen in #266–#268.

## Sessionregeln

`backend.auth.AuthenticationRepository` ist die interne, testbare Grenze für
Konten- und Sessionpflege. Es gibt in dieser Stufe keinen Netzwerk-Endpunkt zur
Kontenpflege und keinen Login-Endpunkt. Spätere Anmeldeverfahren erzeugen eine
Session ausschließlich über diesen Service beziehungsweise eine darauf
aufbauende Fachschicht für die Betreiber-CLI.

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
Betreiberrechte in fachliche Rollen umwandeln. Die weitergehende
Ausschussisolation und Aktionsautorisierung ist Aufgabe von #265.

Angular nutzt die Standard-XSRF-Unterstützung von `HttpClient` mit den
kanonischen Cookie-/Headernamen. Der E2E-Server stellt Sessions ausschließlich
für den isolierten Playwright-Reset bereit; diese Route existiert nicht im
Produktionsserver.
