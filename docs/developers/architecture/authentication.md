# Authentifizierung und Sitzungen

Die Authentifizierungsgrundlage trennt die technische Identität eines Kontos
von fachlichen Ausschussrollen. Ein `user_account` kann optional mit einer
`person` verknüpft sein und separat `is_operator` tragen. Betreiberrechte
erzeugen keine Ausschussmitgliedschaft und damit keine fachlichen Rechte.
Kennwort und verpflichtendes TOTP sind in #266 ergänzt; Passkeys und OIDC
bleiben die getrennten Folgearbeiten #267 und #268.

## Sessionregeln

`backend.auth.AuthenticationRepository` ist die interne, testbare Grenze für
Konten- und Sessionpflege. Konten, Einladungen, Sperrung und Recovery werden
weiterhin ausschließlich über die lokale Betreiber-CLI ausgelöst. Das Backend
stellt dafür keine Netzwerk-Admin-Endpunkte bereit. Die öffentlichen lokalen
Auth-Endpunkte sind auf Login, Einladungsaktivierung und Recovery begrenzt.
Eine erfolgreiche lokale Anmeldung erzeugt eine Session ausschließlich über
den Repository-Service.

Die Konten-, Einladungs-, Sperr- und Recovery-Grundlage für diese Fachschicht
liegt in `backend.admin_service`. Die portable Go-Grenze und ihr
JSON-/Exit-Code-Vertrag sind in der [Betreiber-CLI-Referenz](operator-auth-cli.md)
beschrieben. Der Betreiber bleibt ohne `person_id`; eine Betreiberoperation
verleiht daher niemals eine Ausschussrolle.

Eine Session besteht aus zufälligem opaque Bearer-Material und einem separaten
CSRF-Token. In `auth_session` liegen nur SHA-256-Prüfwerte, nie die Token. Die
Session ist standardmäßig acht Stunden absolut gültig. Über
`LZUG_SESSION_TTL_SECONDS` sind ausschließlich 5 Minuten bis 24 Stunden
zulässig; Cookie und serverseitige Ablaufzeit verwenden denselben Wert. Eine
Rotation widerruft die alte Session atomar und erzeugt eine neue; Logout, Kontensperrung und
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

`/api/health` ist als öffentliches Liveness-Signal bewusst freigegeben und
enthält ausschließlich Status und Self-Link, niemals Fach-, Persistenz- oder
Migrationsdaten. `/api/ready` prüft dagegen die Anwendungs- und
Datenbankbereitschaft und antwortet mit HTTP 200 oder HTTP 503. `/api`, OpenAPI und API-Dokumentation
benötigen eine Session. Die zwingend öffentlichen lokalen Auth-POST-Routen
sind unten einzeln begründet. Alle Fachoperationen benötigen eine gültige Session. HTTP 401 bedeutet
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

## Lokale Anmeldung mit Kennwort und TOTP

`backend.local_auth.LocalAuthService` verarbeitet die fünf öffentlichen
Vorgänge `/api/auth/login`, `/api/auth/invitation/prepare`,
`/api/auth/invitation/activate`, `/api/auth/recovery/prepare` und
`/api/auth/recovery/complete`. Token werden nur im JSON-Body angenommen; sie
erscheinen weder in URLs noch in Fehlern, Logs oder Analytics. Die Antworten
verwenden für unbekannte Konten und falsche Faktoren dieselbe generische
Fehlermeldung.

Bei der Einladungsaktivierung liefert die Anwendung ein zufälliges TOTP-Secret
über die einmalige HTTPS-Antwort. Die Aktivierung ist erst nach Bestätigung
des TOTP-Codes erfolgreich und verbraucht den kurzlebigen Einladungstoken
atomar. Das Secret wird mit Fernet verschlüsselt gespeichert; der Schlüssel
liegt in `LZUG_AUTH_ENCRYPTION_KEY` oder in der mit Modus 0600 geschützten
Datei `.lzug-auth.key` neben der Datenbank. Er muss in der Sicherungs- und
Betriebsdokumentation wie anderes lokales Geheimnis behandelt werden.

Kennwörter werden ausschließlich mit Argon2id gehasht. Die dokumentierten
Startparameter sind `time_cost=3`, `memory_cost=65536 KiB`, `parallelism=4`,
`hash_len=32` und `salt_len=16`; `argon2-cffi` markiert veraltete Parameter
und löst beim erfolgreichen Login einen kontrollierten Rehash aus. Diese
Parameter sind bewusst im Service zentralisiert und dürfen später nur mit
Migration der Betriebs- und Performanceannahmen angepasst werden.

TOTP verwendet `pyotp` mit sechs Stellen, 30-Sekunden-Zeitfenster und einem
akzeptierten Drift von höchstens einem Fenster. Nach erfolgreicher Prüfung
wird das angenommene Zeitfenster atomar als `totp_last_step` fortgeschrieben;
eine Wiederholung desselben Codes kann dadurch nicht erneut anmelden.
Recovery-Codes sind davon fachlich getrennt: Sie werden bei Aktivierung oder
Recovery genau einmal angezeigt, nur als Argon2id-Hash gespeichert und in
einem atomaren Update verbraucht. Ein Betreiber-Recovery-Token aus #269 ist
dagegen ein kurzlebiger, einmaliger Auslöser für die Neuregistrierung der
lokalen Faktoren.

Die lokale Einzelinstanz begrenzt fehlgeschlagene Loginversuche pro
IP-/normalisierter E-Mail-Kombination auf fünf Versuche in fünf Minuten. Bei
Überschreitung wird HTTP 429 mit `Retry-After` geliefert. Das ist ein
prozesslokaler Schutz für eine einzelne Instanz; ein verteiltes Rate-Limit ist
nicht Bestandteil des Self-Hosting-Modells.

Zusätzlich begrenzt die HTTP-Grenze alle öffentlichen Auth-Routen je IP und
Route standardmäßig auf 20 Requests pro 60 Sekunden. Die Grenzen sind über
`LZUG_AUTH_RATE_LIMIT` und `LZUG_AUTH_RATE_WINDOW_SECONDS` konfigurierbar; die
zulässigen Bereiche werden beim Start fail-closed validiert.
