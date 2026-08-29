# ADR-0011: GitHub Wiki als redaktionelle Handbuchoberfläche

## Status

Akzeptiert am 30.07.2026. Superseded by: ADR-0012.

## Kontext

ADR-0007 bündelte versioniertes Markdown-Handbuch und generierte
Code-Referenzen in einem MkDocs-Build. Für die öffentliche Nutzung brauchen
Fachlichkeit, Nutzer, Administration und Entwicklung eine redaktionelle
Handbuchoberfläche. Das GitHub Wiki ist dafür ein separates Git-Repository und
veröffentlicht nur seinen Default-Branch.

Eine Kopie der Wiki-Seiten im Hauptrepository würde zwei Kanons erzeugen und
den Veröffentlichungsstand vom geprüften Wiki-Stand entkoppeln. Gleichzeitig
müssen technische Verträge und generierte Referenzen an ihren bestehenden,
code- beziehungsweise CI-gebundenen Orten bleiben.

## Entscheidung

- Das GitHub Wiki ist die redaktionelle öffentliche Handbuchoberfläche.
- Die Wiki-Seiten leben ausschließlich im separaten Wiki-Repository. Das
  Hauptrepository enthält keine Wiki-Spiegelung.
- Das Hauptrepository enthält nur den portablen Sicherheits-/Link-Validator,
  den manuellen Pre-Publish-Check und den Post-Publish-Check für das tatsächlich
  ausgecheckte Wiki.
- Vor der ersten öffentlichen Mutation prüft ein Maintainer einen konkreten
  Wiki-Branch oder Commit mit dem manuellen Workflow und genehmigt danach die
  Veröffentlichung in den Default-Branch. Das Hauptrepository pusht nicht in
  das Wiki.
- Gollum wird ausschließlich im digest-gepinnten CI-Container eingesetzt. Eine
  Ruby- oder Gollum-Abhängigkeit wird nicht in die Python/npm-Projekttoolchain
  aufgenommen.
- MkDocs bleibt der technische Referenz- und Validierungsbuild. ADRs,
  OpenAPI, Schema, Migrationen, technische Modelle und generierte Referenzen
  werden nicht ins Wiki kopiert.

## Konsequenzen

Der Wiki-Clone muss unabhängig reviewt und veröffentlicht werden. Der
Pre-Publish-Workflow braucht einen Branch, Tag oder Commit als Eingabe; der
Post-Publish-Workflow kann nur nach Initialisierung des GitHub Wikis laufen.
Die redaktionellen Seiten können sich über stabile Repository-Links auf
verbindliche technische Quellen beziehen, ohne diese zu duplizieren.

Die spätere Entscheidung über Pages, Hugo, MkDocs-Ablösung oder eine
Landingpage bleibt #206.

## Alternativen

- **Wiki-Dateien im Hauptrepository spiegeln:** verworfen, weil dadurch zwei
  redaktionelle Kanons entstehen.
- **Automatisch aus dem Hauptrepository ins Wiki pushen:** verworfen, weil die
  öffentliche Mutation nicht an eine Maintainer-Freigabe gebunden wäre.
- **MkDocs als öffentliche Handbuchoberfläche ablösen:** nicht Teil dieser
  Entscheidung; der technische Build bleibt erhalten.

## Referenzen

- [ADR-0007: MkDocs und Code-Referenzen](0007-dokumentation-und-code-referenz.md)
- [Wiki-Publikation](../wiki-publishing.md)
- [GitHub Wiki](https://github.com/lxndrp/lzug/wiki)
