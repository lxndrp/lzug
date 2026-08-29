# ADR-Vorlage

Diese Vorlage ist keine Architekturentscheidung und wird nicht in der Navigation veröffentlicht.
Sie dient ausschließlich als Ausgangspunkt für neue ADRs unter diesem Verzeichnis.

```markdown
# ADR-NNNN: <knapper Entscheidungstitel>

## Datum

YYYY-MM-DD.

## Status

Vorgeschlagen am YYYY-MM-DD.

<!-- Bei vollständiger Ablösung einer fortgeltenden Entscheidung ergänzen:
Supersedes: [ADR-NNNN: Titel](NNNN-dateiname.md). -->

## Kontext

<Welches langfristige Problem oder welche bindende Wahl liegt vor?>

## Entscheidung

<Welche Entscheidung wird getroffen und welche Grenze gilt?>

## Konsequenzen

<Welche dauerhaften Folgen, Verantwortungen und Grenzen ergeben sich?>

## Alternativen (optional)

<Welche relevanten Alternativen wurden verworfen und warum?>

## Referenzen (optional)

<Stabile Verträge, Dokumente oder externe Quellen; keine Issue- oder
Migrationsinventare.>
```

`Datum` ist das Datum der Entscheidung.
Bei rückwirkend dokumentierten ADRs bleibt dort das historische Entscheidungsdatum stehen.
Die Grundstruktur besteht aus Titel, Datum, Status, Kontext, Entscheidung und Konsequenzen in dieser Reihenfolge.
`Alternativen` und `Referenzen` sind optionale Abschnitte für begründete Auswahl beziehungsweise stabile Quellen.

Nach der Annahme wird nur der Status auf `Akzeptiert.` geändert.
Eine vollständige spätere Ablösung ergänzt ausschließlich im Status des alten ADRs `Superseded by: ADR-NNNN.` und trägt im neuen ADR `Supersedes: ADR-NNNN.`
Ein ADR mit abweichender Grundstruktur oder ohne langfristige Entscheidung wird nicht angelegt.
