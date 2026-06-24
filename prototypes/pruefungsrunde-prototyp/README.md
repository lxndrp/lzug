# Prüfwerk – Prototyp „Prüfungsrunde“

Dieser klickbare Frontend-Prototyp bildet den ersten Arbeitsbereich für einen IHK-Prüfungsausschuss ab.

## Start

Die Datei `index.html` in einem aktuellen Browser öffnen. Es werden keine Installation, kein Build-Schritt und keine Internetverbindung benötigt.

## Enthaltene Funktionen

- Übersicht des aktuellen Prüfungsdurchgangs
- Prüflingsverwaltung mit Suche, Fachrichtungsfilter und CSV-Import
- Prüfungsversuch und Kennzeichnung einer mündlichen Ergänzungsprüfung (MEP)
- zusätzlicher Planungstermin je MEP-pflichtigem Prüfling, stets am Ende eines Prüfungstages
- Download einer CSV-Importvorlage
- Duplikaterkennung anhand der IHK-Prüfungsnummer
- Ausschussverwaltung mit Arbeitgeber-, Arbeitnehmer- und Schulseite
- getrennte Modellierung von Mitgliedsstatus und Vorsitzfunktion
- Verwaltung von Prüfungsorten und Räumen
- Planung über Kalenderwochen und konfigurierbare Prüfungen pro Tag
- konfigurierbare Obergrenze für Prüfungstage pro Kalenderwoche (Standard: 3, nur Vorsitz)
- optionale Mittagspause von 12:30 bis 13:30 Uhr
- ganztägige und halbtägige Verfügbarkeiten
- automatische Besetzung mit allen drei Vertreterseiten und zusätzlichem Fallback
- Bevorzugung möglichst voller Prüfungstage; Aufteilung nur bei fehlender Verfügbarkeit
- Verteilung der Prüfer unter Berücksichtigung ihrer bisherigen Belastung
- Prüfungsslots ab 08:30 Uhr im Stundenraster
- verbindliche Bestätigung und dauerhafte Anzeige des Terminplans auf Planung und Übersicht

## Hinweise zum Prototyp

Die Beispieldaten und Änderungen werden ausschließlich im lokalen Browser-Speicher abgelegt. E-Mails, Kalendereinladungen, Anmeldung, Passkeys und Benachrichtigungen an die IHK sind als spätere Backend-Funktionen noch nicht technisch angebunden.

Für einen Produktivbetrieb werden als nächste Schritte ein Server-Backend, eine Datenbank, Authentifizierung, Rollenprüfung, ein E-Mail-/Kalenderdienst und ein revisionssicheres Ereignisprotokoll benötigt.
