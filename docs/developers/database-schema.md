# Datenbankschema

`db/schema.sql` ist die ausführbare Referenz für eine neue Datenbank.
`db/migrations/` ist die chronologische Referenz für Änderungen bestehender
Bestände; die Laufzeit prüft ihre Historie und Integrität. SQLAlchemy-Modelle
unter `backend/models.py` bilden dieselbe Produktstruktur in der Anwendung ab.

Diese Quellen sind gemeinsam maßgeblich. Generierte Code-Referenzen entstehen
beim Dokumentationsbuild. Die Entscheidung für lokale relationale Persistenz
hält [ADR-0001](decisions/0001-lokale-relationale-persistenz.md) fest.

Diese Seite enthält bewusst keine Tabellen-, Feld- oder Typliste. Änderungen
am Datenmodell erfolgen über Modell, Schema und erforderliche Migration
zusammen; ihre fachliche Bedeutung erläutert das
[fachliche Datenmodell](domain-model.md).
