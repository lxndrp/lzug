# ADR-0030: X25519 und AES-GCM für geschützte Artefakte

## Datum

2026-08-30.

## Status

Akzeptiert.

## Kontext

Vollständige Backups enthalten Datenbank, Dokumente und anwendungseigene Schlüssel und benötigen deshalb Vertraulichkeit und Integrität außerhalb der Instanz.
Automatische Sicherungen dürfen nur einen öffentlichen Empfängerschlüssel voraussetzen; der private Schlüssel bleibt extern und wird erst für Prüfung oder Restore geschützt zugeführt.
Vollexporte verwenden denselben Schutzrahmen, können aber für einen anderen autorisierten Empfänger bestimmt sein.

## Entscheidung

lzug schützt Backup und Vollexport mit einem ephemeren X25519-Schlüsselaustausch, HKDF-SHA-256 und AES-256-GCM aus der Python-Bibliothek `cryptography`.
Der ungeschützte versionierte Vorspann ist als Additional Authenticated Data gebunden und enthält nur technisch notwendige Containerwerte sowie den SHA-256-Fingerabdruck des Empfängerschlüssels.
Das vollständige Manifest und alle Nutzdaten liegen in einem unkomprimierten, vollständig inventarisierten ZIP-Paket innerhalb der authentifiziert verschlüsselten Nutzlast.

Öffentliche und private X25519-Schlüssel werden als präfixiertes Base64url-kodiertes rohes 32-Byte-Schlüsselmaterial übergeben.
Der öffentliche Backup-Schlüssel gehört zur Laufzeitkonfiguration; der private Schlüssel wird ausschließlich im stdin-Protokoll des lokalen Adminprozesses angenommen und nie gespeichert oder ausgegeben.

## Konsequenzen

Eine Instanz kann automatische Artefakte erzeugen, ohne Entschlüsselungsgeheimnisse zu besitzen.
Jede Änderung an Vorspann oder Nutzlast und jeder falsche Empfängerschlüssel wird vor Auswertung des Vollmanifests erkannt.
Streaming begrenzt den Speicherbedarf; unkomprimierte Pakete ermöglichen belastbare Größenprüfungen vor der Extraktion.

Der Schutzvertrag hat zunächst genau ein Format und einen Algorithmus-Satz.
Passphrasen, mehrere Empfänger, alternative Algorithmen und Schlüsselverwaltung sind nicht enthalten und erfordern bei späterem Bedarf eine neue Formatversion oder Entscheidung.

## Alternativen

- Symmetrischer Instanzschlüssel: würde für automatische Sicherung und Restore dasselbe dauerhaft verfügbare Geheimnis verlangen.
- Nur dateibasierte Fernspeicherverschlüsselung: könnte die lokale Veröffentlichung eines ungeschützten vollständigen Artefakts nicht verhindern.
- Komprimiertes Archiv: erschwert die sichere Vorabprüfung des benötigten Extraktionsspeichers und ist für den Erstvertrag nicht erforderlich.

## Referenzen

- [Lokaler Admin- und Artefaktvertrag](../data-and-contracts.md#lokaler-admin-und-artefaktvertrag)
- [RFC 7748: Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748)
- [RFC 5869: HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869)
- [NIST SP 800-38D: Galois/Counter Mode](https://csrc.nist.gov/publications/detail/sp/800-38d/final)
