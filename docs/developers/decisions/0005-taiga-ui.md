# ADR-0005: Taiga UI für die Oberfläche

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Eine begrenzte Taiga-UI-Erprobung bestätigte die technische und gestalterische Richtung für eine inkrementelle Migration. Backend, API-Verträge, Routen und fachliche Abläufe blieben dabei unverändert. Taiga UI deckt die produktiven Oberflächenkomponenten ab.

## Konsequenzen

Taiga UI ist die gewählte Komponentenbibliothek. Bewusst verbleiben native oder anwendungseigene Elemente für ISO-Kalenderwochen, Select-Anbindung, vorhandene SVG-Icons sowie das responsive Grid und Tabellenverhalten. Die aktuelle Ausnahmeliste steht unter [Frontend-Ausnahmen](../frontend-exceptions.md); die Git-Historie bewahrt die frühere Prototypbeschreibung.
