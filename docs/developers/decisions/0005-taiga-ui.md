# ADR-0005: Taiga UI für die Oberfläche

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Eine begrenzte Taiga-UI-Erprobung bestätigte die technische und gestalterische Richtung für eine inkrementelle Migration. Backend, API-Verträge, Routen und fachliche Abläufe blieben dabei unverändert. Taiga UI deckt die produktiven Oberflächenkomponenten ab.

## Konsequenzen

Taiga UI ist die gewählte Komponentenbibliothek. Bewusst verbleiben native oder anwendungseigene Elemente für ISO-Kalenderwochen, Select-Anbindung, vorhandene SVG-Icons sowie das responsive Grid und Tabellenverhalten. Die historische Prototypbeschreibung und Ausnahmeliste bleiben unter [taiga-ui-prototype.md](../../taiga-ui-prototype.md) und [taiga-ui-exceptions.md](../../taiga-ui-exceptions.md), sind aber nicht aktiv navigiert.
