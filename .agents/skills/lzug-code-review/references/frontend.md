# Frontend-Prüfperspektive

Einstiege sind `frontend/src/app/`, `frontend/e2e/`, `frontend/package.json` und der zugehörige Lockfile.
Lies die aktuellen Frontendgrenzen aus `docs/developers/components.md`.

- Prüfe Angular-Komponenten, Templates, DI-Lebensdauer, Router, Forms und die eingesetzten Signal-/RxJS-Primitive auf passenden Einsatz.
  Unterscheide abgeleiteten Zustand von Seiteneffekten; fordere keinen Signal- oder Observable-Umbau allein aufgrund persönlicher Präferenz.
- Verfolge Requests, Ereignisse und Änderungen über Routen-, Komponenten- und Operationsgrenzen.
  Prüfe veraltete Antworten, doppelte Mutationen, zerstörte Komponenten, Subscription-Cleanup und das Verhalten bei Wechsel des fachlichen Kontextes.
  Die Wahl von Abbruch-, Warteschlangen- oder Parallelitätsoperatoren muss zum konkreten Lese- oder Schreibvorgang passen.
- Prüfe, ob Transportadapter HTTP, generierte DTOs und Fehler übersetzen und Fach-/UI-Services mit den vorgesehenen Verträgen arbeiten.
  Prüfe TypeScript-Narrowing, Nullzustände und Umgehungen durch `any`, Casts oder unvalidierte JSON-Annahmen.
  Generierten Code nur über den Generator und seine Eingaben beurteilen.
- Prüfe Laden, Leere, Erfolg, Konflikt, Fehler und Wiederholung aus Sicht der nutzenden Person.
  Fehlende Tastaturbedienung, Labels oder Fokusbehandlung sind konkrete Implementierungsbefunde; ein vollständiger UX-Review benötigt einen eigenen Auftrag.
- Prüfe Tests an der vorgesehenen Grenze: Adaptertests für HTTP, Featuretests gegen fachliche Ports und passende Integration-/E2E-Nachweise.
  Plattformprobleme eines Browsers und Fehler der Anwendung anhand reproduzierbarer Evidenz unterscheiden.

Bewerte Frameworkverhalten anhand der im Projekt eingesetzten Angular-/RxJS-/Testwerkzeug-Versionen.
