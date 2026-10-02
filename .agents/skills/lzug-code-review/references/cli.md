# CLI-Prüfperspektive

Einstiege sind `operator-cli/`, insbesondere Command-Registry, Admintransport, Renderer, `go.mod`, Tests und GoReleaser-Konfiguration.
Lies den aktuellen Adminvertrag und die Zuständigkeitsgrenze zum autoritativen Backend.

- Prüfe idiomatisches Go: konkrete Interface-Nutzer, Fehlerketten, `context.Context`, Ressourcenfreigabe, Goroutine-Lebensdauer und begrenzte Parallelität.
  Fehler müssen im Aufrufer sinnvoll klassifizierbar sein; Exitcodes und Standardausgaben bleiben vertraglich nutzbar.
- Prüfe Argumentvalidierung und das gemeinsame Verhalten von direktem und geführtem Einstieg.
  Command-Metadaten, Ausführung und Rendering sollen denselben Vertrag verwenden, ohne Fachregeln aus dem Backend nachzubauen.
- Verfolge Unix-Socket-, SSH- und Subprozesszugriffe einschließlich Timeout, Abbruch, Drain, Streamgrenzen und Protokollversion.
  Ein verlorener Rückkanal beweist keinen fehlgeschlagenen Fachauftrag; automatische Wiederholung verändernder Befehle braucht einen gesicherten Vertrag.
- Prüfe Pfade, Argumentübergabe und Shell-Grenzen auf sichere Nutzung der Go-/System-APIs.
  Diagnose und Fehler dürfen keine Tokens oder privaten Schlüssel offenlegen.
  Bewahre die Trennung zwischen Backend-Artefaktstrom und lokaler kryptographischer Hülle.
- Prüfe Testbarkeit über passende I/O-/Transportgrenzen sowie konkrete Fehler- und Abbruchtests.
  Plattformannahmen benötigen Nachweise für die tatsächlich unterstützten Zielplattformen.
  Zusätzliche Plattformunterstützung, Packaging-Umbauten und SDK-Wechsel sind keine impliziten Reviewaufträge.
