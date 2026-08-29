# ADR-0029: Einheitliches Nygard-Format für Architekturentscheidungen

## Datum

2026-08-29.

## Status

Akzeptiert.

## Kontext

Die bestehenden Architekturentscheidungen wurden historisch in zwei strukturellen Varianten dokumentiert.
Für eine schnelle und nachvollziehbare Prüfung benötigen alle ADRs dieselben leicht auffindbaren Kernelemente.
Die Migration darf dabei weder Entscheidungen neu bewerten noch die historische Gültigkeit, Ablösungen oder Verweise verändern.

## Entscheidung

Alle ADRs verwenden die Nygard-Grundstruktur aus Titel, Datum, Status, Kontext, Entscheidung und Konsequenzen in dieser Reihenfolge.
Das Datum bezeichnet bei rückwirkend dokumentierten ADRs das historische Entscheidungsdatum.
`Alternativen` und `Referenzen` bleiben optionale Abschnitte; vorhandene zusätzliche Abschnitte werden dort beibehalten, wo ihre bisherige Zuordnung erhalten bleibt.

ADR-0001 bis ADR-0028 werden ausschließlich strukturell an diese Grundstruktur angepasst.
Ihre Aussagen, Statusangaben, historischen Hinweise, Alternativen, Kriterien und Referenzen bleiben erhalten oder werden eindeutig einem bestehenden Abschnitt zugeordnet.

## Konsequenzen

Neue und bestehende ADRs haben eine einheitliche Orientierung für Lesende, Reviews und Dokumentationsprüfungen.
Historische Entscheidungen bleiben unverändert nachvollziehbar, weil die Migration keine fachliche Neubewertung und keine neue Ablösung einführt.
Die Vorlage und der Entscheidungsindex weisen gemeinsam auf die verbindliche Struktur hin.

## Alternativen

- Die bestehenden Strukturvarianten beibehalten: würde die Auffindbarkeit der Kernelemente und die formale Prüfung uneinheitlich halten.
- Die historischen Entscheidungen inhaltlich neu schreiben: würde die ausdrücklich gewünschte Trennung von Strukturmigration und Neubewertung verletzen.

## Referenzen

- [arc42: Architecture Decisions](https://docs.arc42.org/section-9/)
- [arc42: Document decisions as Architecture Decision Record](https://docs.arc42.org/tips/9-5/)
