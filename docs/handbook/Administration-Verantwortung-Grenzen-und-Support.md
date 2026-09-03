# Verantwortung, Datenlebenszyklus und Support

Der Betrieb einer eigenen lzug-Instanz überträgt keine Betriebs-, Datenschutz-
oder Supportverantwortung auf eine IHK oder die Maintainer.
Diese Seite ist eine technische Orientierung und keine Rechtsberatung.

Die folgenden Betriebsgrenzen beziehen sich auf den für `v0.6.0`
implementierten Vertrag.
Sie dürfen erst mit einer tatsächlich veröffentlichten und verifizierten
`v0.6.0` oder einer späteren kompatiblen Version angewendet werden.

## Projekt- und Betreiberverantwortung

Das lzug-Projekt veröffentlicht Quellcode, technische Verträge,
Release-Artefakte, Sicherheitshinweise und diese Betriebsanleitung.
Das Projekt betreibt keine dezentralen Instanzen.
Maintainer haben in dieser Rolle keinen vorgesehenen Zugriff auf deren Daten
und entscheiden weder Verarbeitungszwecke noch konkrete Aufbewahrungs- oder
Löschfristen.

Die Organisation, die eine Instanz betreiben lässt und über deren Fachdaten
entscheidet, legt Zweck, Umfang, Zugriffsrollen, Empfänger, Aufbewahrung und
Löschung für ihre Instanz und alle erzeugten Kopien fest.
Sie beauftragt technische Betreiber nur im erforderlichen Umfang und bestimmt,
wer fachliche Daten prüfen oder einen Vollexport empfangen darf.

Die verantwortliche Organisation muss insbesondere selbst klären und umsetzen:

- datenschutzrechtliche Rollen, Rechtsgrundlage, Informationspflichten und
  gegebenenfalls Auftragsverarbeitung;
- zulässigen Personen- und Ausschusskreis sowie Vergabe, regelmäßige Prüfung
  und Entzug fachlicher und technischer Rechte;
- TLS, Reverse Proxy, Host-Härtung, Engine-Zugriff, Sicherheitsupdates und
  Schutz des persistenten Volumes;
- Aufbewahrungs-, Lösch- und Auskunftsverfahren für Fachdaten, Dokumente,
  Benachrichtigungen, Exporte und technische Nachweise;
- Backupplan, Wiederherstellungstests, getrennte Aufbewahrung des privaten
  Empfängerschlüssels, Rotation und sichere Löschung externer Kopien;
- Verträge und Konfiguration für SMTP, Web Push und weitere externe Provider;
- datensparsame Diagnose und die Entfernung realer personenbezogener Daten und
  Secrets aus Supportmeldungen.

## Datenminimierung und Aufbewahrung

- Erfassen Sie nur Daten und Dokumente, die für den festgelegten
  Verarbeitungszweck der Instanz benötigt werden.
- Aktivieren Sie E-Mail, Web Push und persönliche Kalenderfeeds nur, wenn der
  jeweilige Kanal benötigt und betreiberseitig abgesichert wird.
- Vergeben Sie fachliche Ausschussrollen und technische Betreiberrechte
  getrennt, prüfen Sie beide regelmäßig und entziehen Sie nicht mehr benötigte
  Rechte.
- Legen Sie Aufbewahrungsregeln und Löschfreigaben außerhalb von lzug fest.
  Diese Anleitung nennt bewusst keine allgemeingültigen Fristen.
- lzug kann für Prüfungsprotokolle und Ergebnisse ein `retain_until` sowie eine
  begründete Aufbewahrungssperre dokumentieren und verhindert das unbemerkte
  Verkürzen bereits festgelegter Werte.
  Diese Angaben lösen keine automatische Löschung aus und ersetzen keine
  fachliche oder rechtliche Prüfung.
- Prüfen Sie vor jeder Sicherung oder Ausleitung, ob die zusätzliche Kopie für
  den festgelegten Zweck erforderlich ist.
  Ein vorsorgliches Backup unmittelbar vor einer Löschung kann dem Löschziel
  widersprechen und benötigt deshalb eine eigene Freigabe.

## Verfügbare Lösch- und Widerrufsmöglichkeiten

`v0.6.0` stellt keinen allgemeinen Löschlauf und keine Betreiber-CLI zum
selektiven Entfernen von Fachdaten bereit.
Die vorhandenen Funktionen sind enger begrenzt:

| Funktion | Verfügbarer Weg | Grenze |
| --- | --- | --- |
| Prüflingsstammdatum löschen | Fachoberfläche **Prüflinge**, Aktion **Löschen** mit Bestätigung | Abhängige Fachdaten oder Integritätsregeln können die Löschung verhindern; die Aktion löscht keine externen Kopien. |
| Prüfungsort löschen | Fachoberfläche **Prüfungsorte**, Aktion **Löschen** mit Bestätigung | Referenzierte Orte können nicht zuverlässig als eigenständiges Löschziel behandelt werden; gegebenenfalls nur deaktivieren. |
| Prüfungsrunde löschen | Fachoberfläche **Prüfungshalbjahre**, bestätigte Aktion **Leere Entwurfsrunde löschen** | Nur eine offene Entwurfsrunde ohne abhängige Fachdaten kann gelöscht werden. |
| Persönlichen Kalenderzugang widerrufen | Fachoberfläche **Zustellung**, Aktion **Feed widerrufen** | Weitere Abrufe werden verhindert; bereits in externe Kalender kopierte Termine werden nicht entfernt. |
| Benutzerkonto sperren | `lzug-admin disable --account-id <id>` | Das Konto und seine fachlichen Bezüge werden nicht gelöscht; aktive Sitzungen werden widerrufen. |
| Gesamte Instanz außer Betrieb nehmen | Container stoppen und das persistente `/data`-Volume über die verwendete Infrastruktur löschen | lzug bietet keinen eigenen Befehl dafür; Backups, Vollexporte, Fernkopien und Datenträgerreste bleiben getrennt zu behandeln. |

Es gibt insbesondere keine unterstützte automatische Löschung abgeschlossener
Prüfungsrunden, Protokolle, Ergebnisse, Historien, Benachrichtigungen,
Dokumentbestände oder Konten nach einem Datum.
Es gibt auch keinen personenbezogenen Auskunftsexport, keine selektive
Anonymisierung und keinen instanzweiten „Recht auf Löschung“-Schalter.
Rohzugriffe auf SQLite oder einzelne Dateien sind kein unterstütztes
Löschverfahren und können Beziehungen, Nachweise und Dokumentkonsistenz
beschädigen.

## Kontrolliertes Löschverfahren

1. Die verantwortliche Organisation bestimmt Datenumfang, Zweck, geltende
   Aufbewahrungsentscheidung, Sperren und die fachlich freigebende Person.
2. Erfassen Sie alle betroffenen Orte: aktive Instanz, `/data`-Volume, lokale
   Backup- und Exportartefakte, `pre-restore`-Sicherheitsartefakte,
   Zwischenkopien, Fernspeicher und Empfängerkopien.
3. Die fachlich berechtigte Person führt die verfügbare Fachaktion aus und
   prüft das Ergebnis in der Fachoberfläche.
   Ein technischer Betreiber darf daraus kein eigenes fachliches Leserecht
   ableiten.
4. Technische Betreiber, Speicherverantwortliche und Empfänger löschen die
   ihnen zugeordneten Kopien nach der dokumentierten Freigabe und bestätigen
   das Ergebnis gegenüber der verantwortlichen Organisation.
5. Prüfen Sie anschließend sowohl die aktive Instanz als auch das
   Kopieninventar.
   Ein erfolgreicher UI- oder CLI-Schritt belegt weder die Löschung externer
   Kopien noch eine physische sichere Löschung des Datenträgers.

## Backup und Vollexport bleiben getrennt

Ein vollständiges Backup enthält personenbezogene Fachdaten, Dokumente,
Konten, Passwort-Hashes, TOTP-Secrets und den anwendungseigenen
Authentifizierungsschlüssel in verschlüsselter Form.
Es dient ausschließlich der vollständigen Wiederherstellung derselben Instanz
und erhält interne Identitäten, Beziehungen und vorhandene Historien.
Ein Vollexport enthält fachliche Daten und Dokumente, aber keine
Authentifizierungs-, Sitzungs- oder Betriebsgeheimnisse.
Er dient einer autorisierten fachlichen Weiterverwendung und ist kein
Restore-Eingang.
Beide Artefakte benötigen einen eigenen zulässigen Zweck, Zugriffsschutz,
Aufbewahrungszeitraum und Löschweg.

Der instanzweite Vollexport ist keine fachliche Berechtigung des technischen
Betreibers.
Der Betreiber erzeugt ausschließlich ein geschütztes Artefakt für den
ausdrücklich bestimmten öffentlichen Empfängerschlüssel; die CLI zeigt keine
Fachdaten an.
Ein vollständiger Vollexport ist nicht auf eine Person oder einen Ausschuss
einschränkbar.
Bedienung, Inhalt und technische Grenzen stehen unter
[Backup, Restore und Vollexport](Administration-Backup-Pruefung-und-Restore).

## Schlüssel, Ablage und Kopien

| Gegenstand | Verantwortung |
| --- | --- |
| Empfängerschlüssel | Der vorgesehene Empfänger oder eine ausdrücklich beauftragte Schlüsselverwahrung erzeugt das X25519-age-Schlüsselpaar mit `lzug-admin`. Der öffentliche Schlüssel wird über einen verifizierten Weg an den Betreiber gegeben; der private Schlüssel bleibt getrennt von Host, Container, `/data`, Artefakten und nicht autorisierten technischen Betreibern. |
| Ziel und Ablage | Die verantwortliche Organisation bestimmt den zulässigen Zielort. Der technische Betreiber schützt lokale Zwischenstände und kopiert nur dorthin; lzug wählt keinen Fernspeicher. |
| Fernübertragung | Der Betreiber verwendet einen freigegebenen Transportweg, prüft Artefaktname, Empfängerfingerabdruck und Integrität und vermeidet fachliche Inhalte oder private Schlüssel in argv, Logs und Tickets. lzug überträgt nichts automatisch. |
| Aufbewahrung und Rotation | Die verantwortliche Organisation legt je Artefaktart die benötigte Dauer fest. lzug plant und rotiert nicht. Bei Schlüsselrotation werden neue Artefakte mit dem neuen öffentlichen Schlüssel erzeugt; alte Artefakte werden nicht automatisch umgeschlüsselt und benötigen ihren bisherigen privaten Schlüssel bis zu ihrer Löschung. |
| Löschung | Betreiber, Speicherverantwortliche und Empfänger löschen ihre jeweiligen lokalen, entfernten und temporären Kopien nach Freigabe. lzug löscht veröffentlichte Artefakte nicht automatisch und kann die Löschung fremder Speicher nicht nachweisen. |

Der private Schlüssel wird nur lokal von `lzug-admin` aus einer geschützten
Datei, ausdrücklich gewähltem stdin oder einer verdeckten TTY-Eingabe gelesen.
Er wird weder dem Container noch dem Python-Backend zugeführt.
Wenn der technische Betreiber nicht zum fachlichen Empfängerkreis gehört, muss
der Schlüsselinhaber die Prüfung selbst oder über einen gesondert autorisierten
geschützten Betriebsweg ausführen.
Die bloße technische Kontrolle über Host, Engine oder Volume begründet kein
fachliches Leserecht.

Die öffentliche Demo und das Repository verwenden ausschließlich synthetische
Daten.
Übertragen Sie niemals reale Ausschussdaten in Demo-, Test- oder
Supportsysteme.

## Bekannte Grenzen von `v0.6.0`

- `lzug` bleibt ein nicht produktreifer Quellcode-Prototyp ohne Verfügbarkeits-
  oder Support-SLA.
- Die Referenz ist eine einzelne Instanz mit SQLite und lokalem `/data`-Volume;
  Hochverfügbarkeit, Multi-Node-Betrieb, Kubernetes und eine zentrale
  Mandantenflotte sind nicht enthalten.
- Das Image terminiert kein TLS und verwaltet keinen Reverse Proxy, DNS oder
  Zertifikatslebenszyklus.
- Backupplanung, Rotation, Offsite-Übertragung und Schlüsselverwaltung sind
  nicht automatisiert.
- Es gibt keine automatische Aufbewahrungsauswertung, Löschwarteschlange,
  Artefaktlöschung oder Löschbestätigung für externe Speicher.
- `v0.6.0` erzeugt keine X25519-Empfängerschlüssel über `lzug-admin`;
  alte Artefakte benötigen den dokumentierten v0.6-Wiederherstellungspfad.
- Restore unterstützt nur den dokumentierten Vorwärtspfad auf gleiche oder
  neuere kompatible Schemastände; es gibt keine Datenbank-Downgrade-Migration.
- `rollback` ist nur eine nicht mutierende Kompatibilitätsfreigabe für ein
  älteres Release und verändert weder Schema noch Fachdaten.
- `v0.5.0` und ältere Releases enthalten den Lifecycle-Befehl nicht und sind
  daher kein CLI-Rollbackziel.
- Ein Vollexport kann nicht als Backup wiederhergestellt werden.
- Ein Vollexport ist nur instanzweit verfügbar; Teil-, Ausschuss- und
  personenbezogene Exporte gehören nicht zum Vertrag.
- Passkeys und OIDC sind nicht Bestandteil der Authentifizierungsbaseline;
  vorhanden sind lokale Kennwort-/TOTP-Authentifizierung und Recovery-Codes.
- Betreiberkonten verleihen keine fachliche Ausschussrolle.
- Es gibt keine validierte Kapazitäts- oder Performancezusage für reale
  Datenmengen.

## Technische Diagnose

Führen Sie vor einer Meldung aus:

```sh
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" status
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" config
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" doctor
"$ENGINE" compose -f compose.yaml ps
```

Eine Fehlermeldung sollte Release-Version, CLI-Build-Metadaten, Engine und
Version, Betriebssystem/Architektur, betroffenen Schritt, Exit-Code und die
geheimnisfreie JSON-Fehlerklasse enthalten.
Fügen Sie nur die zur Reproduktion nötigen, bereinigten Logzeilen bei.
Senden Sie keine Datenbank, Dokumente, Artefakte, Schlüssel, Tokens,
Zugangsdaten, E-Mail-Adressen oder sonstigen personenbezogenen Inhalte.

## Supportwege

- Reproduzierbare Fehler und Verbesserungen:
  [GitHub-Issuevorlagen](https://github.com/lxndrp/lzug/issues/new/choose)
- Bereits bekannte Fehler und Grenzen:
  [offene Issues](https://github.com/lxndrp/lzug/issues)
- Veröffentlichte Versionen und Assets:
  [GitHub Releases](https://github.com/lxndrp/lzug/releases)
- Vertrauliche Sicherheitsmeldung, niemals als öffentliches Issue:
  [Private Vulnerability Reporting](https://github.com/lxndrp/lzug/security/advisories/new)
- Unterstützte Sicherheitsstände und Meldeinhalt:
  [SECURITY.md](https://github.com/lxndrp/lzug/blob/master/SECURITY.md)

Es gibt keine zugesicherte Reaktions- oder Behebungsfrist, individuelle
Einrichtungsleistung oder fachliche Beratung durch eine IHK.
