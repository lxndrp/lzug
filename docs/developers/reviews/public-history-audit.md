# Prüfung der öffentlichen Git-Historie

Diese Seite dokumentiert den reproduzierbaren, ausschließlich prüfenden Audit
für GitHub Issue #188. Sie enthält keine Namen, E-Mail-Adressen, Domains,
Telefonnummern, Anschriften, Organisationsnamen oder Matchwerte. Mirror,
Ref-Inventare, Scanner-Rohdaten und das Nachweis-Bundle liegen geschützt
außerhalb des Repositorys.

## Ergebnis vom 29. Juli 2026

Der geprüfte Kandidat ist
`ffd4840024ed2c15c02244c9755423dad73ede26` auf `master`. Das Ergebnis ist ein
**NO-GO für die öffentliche Freigabe**. Der Audit hat keine
Credential-Kandidaten gefunden, aber bestätigte veröffentlichungshemmende
personenbezogene und organisatorische Daten sowie unerwartete historische
Datenbank-Blobs.

| Prüfgrundlage | Ergebnis |
| --- | --- |
| Remote und Mirror | Exakte Übereinstimmung der Objekt-IDs für 2 Heads, 0 Tags, 81 Pull-Request-Head-Refs und 0 Pull-Request-Merge-Refs |
| Erreichbare Historie | 349 Commits, 1.238 Blobs und 1.220 Trees |
| Gitleaks | Version `8.30.1`, 0 Befunde über `--all --full-history`, Ausgabe vollständig redigiert |
| TruffleHog | Version `3.96.0`, 3.394 Chunks, 0 verifizierte und 0 unverifizierte Befunde |
| Eigener Inhaltsaudit | 93 von 93 geschützten Readiness-Vergleichswerten in Blobs und Diffs bestätigt |
| Diffs und Löschungen | 84.843 geänderte Zeilen und 23 historisch gelöschte Pfade geprüft |
| Commit-Identitäten | 5 unterschiedliche Namen und 4 E-Mail-Adressen über 3 Domains; 1 Domain gehört zur Code-Hosting-Noreply-Klasse, 2 zur benutzerdefinierten oder organisatorischen Klasse |
| Binär- und Größenprüfung | 3 Binär-Blobs: 1 erwartetes Icon und 2 unerwartete SQLite-Datenbanken; 57 Blobs ab 100 KiB, kein Blob ab 1 MiB |

Die Inhaltsprüfung speichert nur Kategorie, Anzahl eindeutiger Blobs und
abstrakte Top-Level-Komponenten. Sie bestätigte folgende Kategorien:

| Kategorie | Vorkommen | Eindeutige Blobs |
| --- | ---: | ---: |
| Geschützte Readiness-Vergleichswerte | 3.183 | 389 |
| E-Mail-Adressen | 2.114 | 85 |
| Telefonnummern | 192 | 15 |
| Organisationsnamen mit Rechtsform | 174 | 54 |
| Postanschriften | 46 | 34 |

Die zwei SQLite-Blobs enthalten allein 369 Vorkommen geschützter
Readiness-Werte, 40 E-Mail- und 139 Telefonnummern-Treffer. Die Zählung dient
dem Reichweitennachweis; sie ist keine Aussage über die Anzahl natürlicher
Personen.

Alle fünf Inhaltskategorien und beide SQLite-Blobs sind aus beiden Heads und
allen 81 Pull-Request-Head-Refs erreichbar. Damit reicht ein Rewrite der
normalen Branches im bestehenden GitHub-Repository nicht aus: Die von GitHub
verwalteten Pull-Request-Refs würden die betroffenen Objekte weiterhin
erreichbar halten.

TruffleHog konnte nach dem erfolgreichen Scan zwei temporäre
Aufräumoperationen nicht ausführen, weil die Codex-Sandbox keine fremden
Prozess-IDs bereitstellt. Der Scanner beendete den Lauf erfolgreich; ein
anschließendes `git fsck`, der erneute Ref-Abgleich und der Hash des
Mirror-Bundles waren unverändert.

## Verbindlicher Auftrag an #190

Issue #190 muss vor einer öffentlichen Freigabe:

1. alle 93 bekannten Readiness-Werte aus sämtlichen erreichbaren historischen
   Objekten entfernen; die Bereinigung des aktuellen Datenbestands durch #189
   ersetzt diesen Historien-Schritt nicht;
2. beide historischen SQLite-Blobs vollständig entfernen;
3. alle 2 Heads und 81 Pull-Request-Head-Refs berücksichtigen;
4. einen neuen, sauberen Public-Repository-Ursprung verwenden, sofern GitHub
   nicht vorab belastbar bestätigt und anschließend nachweist, dass alle
   betroffenen serververwalteten Pull-Request-Refs und Objekte im bestehenden
   Repository entfernt wurden;
5. die drei menschlichen oder nicht klassifizierten Commit-Namen und die zwei
   benutzerdefinierten oder organisatorischen E-Mail-Domänen ausdrücklich für
   die Veröffentlichung freigeben oder die Identitäten im genehmigten
   Bereinigungsverfahren ersetzen;
6. den bereinigten Kandidaten erneut mit denselben Ref-, Secret-, PII-,
   Metadaten-, Binär- und Größenprüfungen untersuchen und neue Mirror- und
   Nachweis-Hashes festhalten.

Aus #188 folgt keine Credential-Rotation: Beide unabhängigen Secret-Scanner
lieferten null Kandidaten. Sollte ein späterer Lauf einen plausiblen
Credential-Fund melden, wird der Lauf angehalten und Rotation oder Widerruf
vor jeder weiteren Historienarbeit entschieden.

## Prüfgrundlage und Hashes

| Nachweis | SHA-256 |
| --- | --- |
| Mirror-Bundle | `1fe0483bd97b8abd8cf19e26394885b2db028cac85c0ad2b93e349fcc7cd1a01` |
| Geschütztes Nachweis-Bundle | `a1b2338871ea330a117183b04fa7224c3158382d22eb9f9543a66f24442b6201` |
| Sanitisiertes Ergebnis-JSON | `613f5098c89163aff6ac61e088b62b2e156a909383af818ef6bddd2762a55b9f` |
| Audit-Skript | `e15df05797375c8e830be12afc1337505dd19e56cf53c8c925e3479ec3576cc0` |
| Gitleaks-Regeldatei | `e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf` |
| Geschützter Satz bekannter Werte | `12c55ae9469d1a6657349202ef08669477fef8ce73b58ed7a8955ad55a095de5` |
| Remote- und Mirror-Ref-Inventar | `04a581ed67922a8cff397e46f12bdc97bdd513ba9c0aa7bc1b3c95faa8cd2d63` |

Gitleaks `8.30.1` verwendete die Regeldatei des gleichnamigen Release-Tags.
TruffleHog `3.96.0` verwendete seine eingebauten Detektoren ohne automatische
Updates. Beide Release-Archive wurden vor dem Einsatz gegen die veröffentlichten
Prüfsummendateien verifiziert. Der eigene Audit lief mit Python `3.14.6` und
Git `2.55.0`.

## Reproduzierbarer Ablauf

Der Arbeitsbereich muss außerhalb des Repositorys liegen, nur für die prüfende
Person zugänglich sein und genügend Schutz für PII und mögliche Credentials
bieten. Das folgende Beispiel setzt einen bereits geschützten Pfad in
`AUDIT_ROOT` voraus:

```sh
git clone --mirror https://github.com/lxndrp/lzug.git "$AUDIT_ROOT/lzug.git"
git -C "$AUDIT_ROOT/lzug.git" fetch --prune origin \
  '+refs/heads/*:refs/heads/*' \
  '+refs/tags/*:refs/tags/*' \
  '+refs/pull/*:refs/pull/*'
```

Das authentifizierte `git ls-remote --refs`-Inventar für Heads, Tags und
Pull-Request-Refs wird sortiert mit `git for-each-ref` aus dem Mirror
verglichen. Erst bei exakter Übereinstimmung entsteht das Mirror-Bundle:

```sh
git -C "$AUDIT_ROOT/lzug.git" bundle create "$AUDIT_ROOT/lzug-mirror.bundle" --all
git -C "$AUDIT_ROOT/lzug.git" bundle verify "$AUDIT_ROOT/lzug-mirror.bundle"
```

Die Secret-Scanner laufen mit festen Versionen. Reports gehen ausschließlich
in den geschützten Arbeitsbereich; Gitleaks redigiert Matchwerte vollständig:

```sh
gitleaks git "$AUDIT_ROOT/lzug.git" \
  --log-opts='--all --full-history' \
  --config="$AUDIT_ROOT/gitleaks.toml" \
  --redact=100 --report-format=json \
  --report-path="$AUDIT_ROOT/gitleaks.json" \
  --max-archive-depth=2

trufflehog git --bare --json --no-update --no-color \
  --fail-on-scan-errors \
  --results=verified,unknown,unverified,filtered_unverified \
  "file://$AUDIT_ROOT/lzug.git"
```

Der zusätzliche Scan erhält bekannte Werte über eine geschützte externe Datei.
Das Skript gibt keinen dieser Werte wieder:

```sh
python scripts/audit-public-history.py \
  --git-dir "$AUDIT_ROOT/lzug.git" \
  --known-values "$AUDIT_ROOT/known-values.txt" \
  --output "$AUDIT_ROOT/public-history-audit.json"
```

Das Skript prüft alle erreichbaren Blobs einschließlich extrahierter
Binärstrings, den vollständigen Diffstrom, gelöschte Pfade,
Author-/Committer-Metadaten, E-Mail-Domänenklassen, Dateiendungen und
Objektgrößen. Sein Ergebnis bleibt sanitisiert; die geschützte Rohgrundlage
wird nicht versioniert.
