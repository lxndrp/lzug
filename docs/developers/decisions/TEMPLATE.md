# ADR-Vorlage

Diese Vorlage ist keine Architekturentscheidung und wird nicht in der Navigation veröffentlicht.
Sie bietet eine Orientierung für neue ADRs unter diesem Verzeichnis.
Abschnitte, Titel und Statuswortlaut dürfen dem Inhalt folgen, solange
Entscheidung, aktueller Stand und Beziehungen zu früheren Entscheidungen
verständlich bleiben.

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
Titel, Datum, Status, Kontext, Entscheidung und Konsequenzen sind übliche
Orientierungspunkte; ihre genaue Form und Reihenfolge ist nicht vorgeschrieben.
`Alternativen` und `Referenzen` helfen bei Bedarf, Auswahl und Quellen
nachvollziehbar zu machen.

Ein Status soll den Entscheidungsstand klar benennen.
Bei einer vollständigen späteren Ablösung sollen die betroffenen ADRs den
Zusammenhang nachvollziehbar festhalten und aufeinander verweisen.
Links werden mit dem Dokumentationsbuild geprüft.
