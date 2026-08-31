# ADR-0025: Kein InSpec-Infrastruktur-Harness

## Datum

2026-08-25.

## Status

Abgelehnt.

## Kontext

`lzug` prüft seine Infrastruktur bereits auf drei getrennten Ebenen:

- OpenTofu-Tests validieren den Offline-IaC-Vertrag der Azure-Demo.
- Python-Vertragstests prüfen Compose-Policy, Deploymentlogik und die
sicherheitsrelevanten GitHub-Workflowgrenzen.
- Shell-Smokes orchestrieren Docker oder Podman und belegen am realen Image
Health, nicht privilegierte Ausführung, Ports, Mounts sowie Persistenz über Restart und Stop/Start.

Issue #398 untersuchte, ob Chef InSpec diese Nachweise durch einen gemeinsamen, deklarativen und ausschließlich lesenden Infrastruktur-Harness sinnvoll ergänzen kann.
Der Harness sollte OCI-Image, lokale Compose-Referenz und die bereitgestellte Azure-Demo abdecken, ohne Client-Secret, neue Azure-Rollen oder eine vorab festgelegte dauerhafte Ruby-Abhängigkeit.

## Spike und Befund

Ein isoliertes Profil außerhalb des Repositorys modellierte zwei repräsentative Controls:

- Image: Nutzer `10001:10001`, Port `8000/tcp`, Healthcheck und OCI-Labels.
- Compose: laufender Service, nicht privilegierte Ausführung, veröffentlichter
Port und beschreibbarer Mount `/data`.

Der repräsentative Kern bestand aus InSpec-eigenen Docker-Ressourcen:

```ruby
describe docker_image(input("image_reference")) do
  its(["Config", "User"]) { should eq "10001:10001" }
  its(["Config", "Healthcheck", "Test"]) do
    should eq ["CMD", "python", "-m", "backend.healthcheck"]
  end
end

describe docker.object(input("compose_container")) do
  its(["HostConfig", "Privileged"]) { should cmp false }
  its(["NetworkSettings", "Ports", "8000/tcp"]) { should_not be_empty }
end
```

Das reale Image wurde mit `task quality:oci` erfolgreich gebaut.
Für den isolierten Check wurde das offizielle Image `chef/inspec:5.24.23` mit dem Digest `sha256:eb06cfc8ba8cc21807dc664a6783a21853ea3e2ed958276eaf45a96d086b7a7d` geladen.
Der erste `inspec check` erreichte die Controls nicht, weil die temporäre Profilmetadatei den kombinierten Versionsbereich in einer von RubyGems nicht akzeptierten Schreibweise enthielt.
Dieser Spikefehler ist kein Produktbefund und wird nicht als Begründung für die Entscheidung verwendet; auf weitere Runtime-Experimente wurde verzichtet, weil die nachfolgenden Integrationsgrenzen bereits ein NO-GO ergeben.

Die Controls sind mit InSpec grundsätzlich ausdrückbar.
Sie duplizieren aber die vorhandenen Image- und Compose-Assertions.
Die bestehenden Smokes belegen zusätzlich fachliche Readiness und Persistenzabläufe, die ausdrücklich nicht nach InSpec verlagert werden sollen.
Die notwendige Orchestrierung für Build, Start, temporäre Volumes und Cleanup bliebe deshalb unverändert in Shell.

InSpec 7 liefert Docker- und Podman-Ressourcen als getrennte Ruby-Gems aus.
Damit müsste `lzug` zwei engine-spezifische Resource-Packs sowie die Ruby-/InSpec-Laufzeit pflegen.
Die aktuelle Chef-Paketierung verlangt abhängig von der Distribution außerdem einen Lizenzschlüssel; das lizenzfreie Habitat-Paket führt stattdessen Habitat als zusätzliche Toolchain ein.
Das offizielle Spike-Image ist ausschließlich `linux/amd64`, während die lokale Entwicklung beide Container-Engines ohne eine solche InSpec-Plattformgrenze unterstützt.

Das Azure-Resource-Pack kann ohne `AZURE_CLIENT_SECRET` das Token einer zuvor angemeldeten Azure CLI verwenden.
Es ist damit nach `azure/login` grundsätzlich mit der bestehenden GitHub-OIDC-Föderation kompatibel.
Für die Container App reicht die vorhandene benutzerdefinierte Rolle mit `Microsoft.App/containerApps/read`.
Ein generischer Control kann damit Region, Tags, Konfiguration, Skalierung, Ingress und das im App-Dokument enthaltene `EmptyDir`-Volume lesen.
Resource-Group-Tags, das Container-App-Environment und eigenständige Storage-Ressourcen liegen dagegen außerhalb des absichtlich auf eine Container App begrenzten Scopes.
Ein Harness für die gesamte von `lzug` verantwortete Azure-Infrastruktur würde deshalb breitere Leserechte benötigen; die für #398 betrachteten App-Controls selbst erfordern keine RBAC-Erweiterung.

| Kriterium | Bestehender Nachweis | InSpec-Folge |
| --- | --- | --- |
| Image und Runtime | Docker-/Podman-Smokes prüfen reale Runtime, Health und Metadaten | deklarativer, aber doppelter `inspect`-Nachweis |
| Compose | Standard-Compose-Prüfung, getestete Python-Policy und Ablauf-Smoke | zusätzliche Engine-Resource-Packs; Shell-Orchestrierung bleibt |
| Azure-IaC | `tofu test`, Validierung und gemockter Plan ohne Cloudzugriff | kein Ersatz für den Offline-Vertrag |
| Azure-Livezustand | gezielte Azure-CLI-/Python-Abfragen nach OIDC | generische App-Controls möglich; ein darüber hinausgehender Scope erfordert breitere RBAC-Rechte |
| Toolchain | Python, Node.js, Go, Task, OpenTofu und Container-Engine sind bereits vorhanden | Ruby, InSpec, Resource-Packs sowie Lizenz- oder Habitat-Verwaltung |
| Laufzeit und Kosten | vorhandene Jobs teilen Build und Image | zusätzlicher Image-Pull, Runner-Zeit und Pflege; keine relevante Azure-Abfragegebühr |

## Entscheidung

Chef InSpec wird für `lzug` nicht eingeführt.
Es entstehen kein versioniertes InSpec-Profil, keine Ruby- oder Resource-Pack-Abhängigkeit, kein zusätzlicher Task oder CI-Job und keine Azure-RBAC-Erweiterung.

Die Zustandsassertions bleiben bei den bereits verantwortlichen Ebenen:

- Image- und Runtime-Invarianten in den vorhandenen Container-Smokes,
- Compose-Struktur in Standardprüfung und getesteter Python-Policy,
- notwendige Lifecycle- und Persistenzorchestrierung in Shell,
- Azure-IaC in OpenTofu-Tests und
- gezielte Livezustandsprüfungen nach GitHub OIDC in Azure CLI oder Python.

Diese Trennung verhindert, dass ein einheitlich wirkender Harness die tatsächlich unterschiedlichen Offline-, Runtime- und Cloud-Verträge verdeckt.

## Alternativen

- **InSpec nur für Docker einführen:** Die Controls wären lesbarer, würden aber
vorhandene Assertions duplizieren und Podman nicht mit demselben Resource-Pack abdecken.
- **InSpec für die gesamte Azure-Resource-Group ausführen:** Das würde die
gewünschten Tags und abhängigen Ressourcen erreichen, erfordert aber eine breitere Leserolle als die bestehende Container-App-Identity.
- **Ein separates InSpec-OIDC-Workflowziel anlegen:** Technisch könnte es das
Azure-CLI-Token aus `azure/login` verwenden.
Ein zusätzlicher geschützter Workflow und dessen Toolchain liefern ohne neue Controls keinen Mehrwert.
- **Gezielte Azure-CLI-/Python-Controls ergänzen:** Das bleibt die bevorzugte
Folgeoption, sobald ein konkreter, heute nicht belegter Livezustand geprüft werden muss.
Sie nutzt die bestehende OIDC-Kette und kann auf die minimal erlaubte Ressource begrenzt werden.

## Konsequenzen

Der heutige Qualitätslauf, die unterstützten Container-Engines und die least-privilege OIDC-Identity bleiben unverändert.
Es entstehen keine neuen Azure-Ressourcen, Rollen, Secrets, Lizenzkosten oder Cloudabfragen.

InSpec kann neu bewertet werden, wenn mehrere unabhängige Infrastrukturziele dieselben deklarativen Controls benötigen, eine lizenz- und plattformverträgliche Distribution ohne zusätzliche Toolchain verfügbar ist und die dafür notwendigen Leserechte bereits aus einem konkreten Betriebsvertrag folgen.
Eine solche Neubewertung muss erneut den Mehrwert gegenüber den vorhandenen OpenTofu-, Python-, Shell- und Compose-Nachweisen belegen.

## Referenzen

- [Issue #398](https://github.com/lxndrp/lzug/issues/398)
- [Chef InSpec 7 installieren](https://docs.chef.io/inspec/7.1/install/)
- [Chef-Lizenzschlüssel](https://docs.chef.io/licensing/license_key/)
- [InSpec-Docker-Resource-Pack](https://docs.chef.io/inspec/resource_packs/docker/)
- [InSpec-Podman-Resource-Pack](https://docs.chef.io/inspec/resource_packs/podman/)
- [InSpec-Azure-Resource-Pack](https://github.com/inspec/inspec-azure)
- [Demo-Promotion und Deployment](../delivery.md#demo-promotion-und-deployment)
- [ADR-0009: Toolchain und Entwicklungs-Tasks trennen](0009-toolchain-und-entwicklungs-tasks.md)
