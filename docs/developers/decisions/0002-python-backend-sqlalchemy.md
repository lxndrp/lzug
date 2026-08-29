# ADR-0002: Python-Backend mit SQLAlchemy

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Der erste Backend-Prototyp entschied sich für Python, SQLite und SQLAlchemy 2.x.
HTTP- und Fachcode arbeiten über SQLAlchemy-Modelle, Repositories und einen kleinen Store-Adapter statt über handgeschriebene fachliche SQL-Abfragen.

`backend/database.py` kapselt Engine, Sessions und Initialisierung; `models.py`, `repositories.py`, `store.py` und `planning.py` trennen Persistenz, Ressourcen und Planungslogik.

## Konsequenzen

Das relationale Modell ist lokal ausführbar und von SQLite-spezifischen APIs entkoppelt.
Die aktive Architekturreferenz liegt unter [Backend und Datenzugriff](../architecture/backend.md); die Git-Historie bewahrt den früheren Prototypbericht.
