# Öffentliche Domains und TLS

Dieses Dokument beschreibt den repositoryseitigen Vertrag und den Betreiberablauf
für die öffentliche Landingpage und die flüchtige Demo. Es aktiviert weder DNS,
GitHub Pages noch Azure. Jede externe Änderung bleibt ein separates
Maintainer-Gate.

## Dauerhafte Namen

Der gemeinsame Namensraum lautet `repertoire.papaspyrou.name`.

| Zweck | Dauerhafter Name | Zustand |
| --- | --- | --- |
| GitHub Pages | `lzug.repertoire.papaspyrou.name` | verbindlich entschieden |
| Azure-Demo | `demo.lzug.repertoire.papaspyrou.name` | verbindlich entschieden |
| Namensraum-Wurzel | `repertoire.papaspyrou.name` | kein Portal im Scope |

Die bestätigte Demo-Domain hält Landingpage und Anwendung als getrennte Origins im
gleichen Projektnamensraum. Der Azure-Standardname (`*.azurecontainerapps.io`)
ist kein Produktvertrag und darf nicht als `DEMO_URL` übernommen werden.

## Kleine Freigabegates

1. **Account und DNS:** `repertoire.papaspyrou.name` im GitHub-Account
   verifizieren. Den Nachweis und die DNS-Zuständigkeit read-only prüfen.
2. **Pages-DNS:** genau einen CNAME für `lzug.repertoire.papaspyrou.name` auf
   `lxndrp.github.io` anlegen. Kein Wildcard-Eintrag und keine Weiterleitung
   von `stage.papaspyrou.name/lzug/`.
3. **Pages-Konfiguration:** die Custom Domain am Repository setzen und
   read-only prüfen, dass CNAME, `build_type=workflow` und das erwartete
   Repository-Artefakt zusammenpassen.
4. **Pages-TLS:** erst nach nachgewiesener Zertifikatsbereitstellung
   `https_enforced=true` setzen. Danach HTTP, HTTPS, Zertifikatskette und
   kanonische Root-URL prüfen.
5. **Demo-Domain:** für `demo.lzug.repertoire.papaspyrou.name` den
   Azure-Custom-Domain-/Zertifikatsplan erstellen. DNS, Zertifikat und
   HTTPS-Erreichbarkeit jeweils separat read-only nachprüfen.
6. **Demo-Aktivierung:** die einzige nicht-sensitive Repository-Variable
   `DEMO_URL` auf denselben HTTPS-Origin setzen und im geschützten GitHub-
   Environment `demo` keinen gleichnamigen Override führen. Erst danach
   OpenTofu-Plan, Deployment und Browsernachweis freigeben.

Vor jedem Gate wird der aktuelle externe Zustand erneut gelesen. Eine
Abweichung stoppt den Ablauf; es wird kein Write durch einen lokalen
Konfigurationswert ersetzt.

## Repositoryvertrag

- Die Publication-Base-URL ist exakt
  `https://lzug.repertoire.papaspyrou.name` und liegt an der Domainwurzel.
- `DEMO_URL` ist genau eine nicht-sensitive, nicht imagegebundene
  Repository-Variable mit dem Wert
  `https://demo.lzug.repertoire.papaspyrou.name`. Publication und Demo-
  Deployment lesen dieselbe Variable; das Environment `demo` darf keinen
  gleichnamigen Override enthalten. Der sichere Placeholder
  `https://demo.example.invalid` ist nur für PR-/Push-Buildprüfungen der
  Publication zulässig und wird vor jeder echten Veröffentlichung oder Demo-
  Mutation fail-closed abgewiesen.
- OpenTofu setzt `LZUG_CORS_ALLOWED_ORIGINS` ausschließlich auf die exakte
  Pages-Origin `https://lzug.repertoire.papaspyrou.name`. Der Pfad `/` gehört
  nicht zur Origin.
- GitHub-Workflow und Demo-Validator weisen HTTP, Pfade, Credentials,
  Query-/Fragment-Teile, Wildcards, `stage.papaspyrou.name`,
  `lxndrp.github.io` und Azure-Standard-FQDNs zurück.
- Azure Container Apps verwendet weiterhin
  `allow_insecure_connections = false`. Die dauerhafte Custom Domain braucht
  zusätzlich einen separat geprüften TLS-/Zertifikatsnachweis.
- CORS ist keine Herkunftsweiterleitung: Die Demo-Origin wird nie als
  zusätzliche erlaubte CORS-Origin eingetragen.

## DNS-, Zertifikats- und Betreiberverantwortung

Die für `papaspyrou.name` zuständige Person verwaltet einzelne CNAMEs und
entfernt keine bestehenden persönlichen Pages-Einträge ohne vorherigen
Nachweis der lzug-Zielauflösung. Der GitHub-Repository-Maintainer verwaltet
Domainverifizierung, Pages-Custom-Domain, Zertifikatsstatus und
`https_enforced`. Der Repository-Maintainer verwaltet die Repository-Variable
`DEMO_URL` und den Ausschluss eines gleichnamigen Environment-Overrides. Der
Demo-Operator verwaltet die bestätigte Azure-Custom-Domain, das Zertifikat und
die Verlängerungsüberwachung.

Ein Live-Nachweis muss mindestens enthalten:

- DNS-Antwort des einzelnen CNAME ohne Wildcard oder konkurrierende Account-
  Origin,
- Pages-API-Zustand mit passendem CNAME, Zertifikatsstatus und HTTPS-Zwang,
- erfolgreiche HTTPS-Anfrage an `/` ohne HTTP-Ausweichadresse,
- Demo-HTTPS-Anfrage an `/api/health` und `/api/ready`,
- Browser-Origin `https://lzug.repertoire.papaspyrou.name` im CORS-Vertrag,
- denselben Demo-Origin in der Repository-Variable `DEMO_URL`, dem
  Deployment-Environment ohne Override und dem Landingpage-Artefakt.

Bis dieser Nachweis vollständig und freigegeben ist, bleibt #127 offen und
werden weder Pages-Dispatch noch Azure-Deployment oder OpenTofu-Apply
ausgeführt.
