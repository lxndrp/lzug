# frozen_string_literal: true

# Load the published GitHub Wiki through the same Gollum library that renders it.
# The workflow supplies Gollum in an isolated, pinned container; it is not a
# dependency of the lzug Python/npm project.
require "gollum-lib"

wiki_root = ARGV.fetch(0)
wiki_ref = ARGV[1]
wiki_options = wiki_ref ? { ref: wiki_ref } : {}
wiki = Gollum::Wiki.new(wiki_root, **wiki_options)
pages = wiki.pages
required = %w[
  Home.md
  _Sidebar.md
  Fachlichkeit.md
  Fachlichkeit-Kernprozesse.md
  Fachlichkeit-Rollen-und-Verantwortlichkeiten.md
  Fachlichkeit-Glossar.md
  Prozess-Pruefungshalbjahr-planen.md
  Prozess-Zulassung-und-Antraege-bewerten.md
  Prozess-Schriftliche-Pruefungen-organisieren.md
  Prozess-Muendliche-Pruefung-planen-und-durchfuehren.md
  Prozess-Pruefungsleistungen-bewerten.md
  Prozess-Ergebnis-feststellen-und-bekanntgeben.md
  User-Journey-Pruefungshalbjahr-planen.md
  User-Journey-Verfuegbarkeit-melden.md
  User-Journey-Muendlichen-Pruefungstag-vorbereiten-und-durchfuehren.md
  User-Journey-Dokumentation-individuell-bewerten.md
  User-Journey-Praesentation-und-Fachgespraech-bewerten.md
  User-Journey-Ergebnis-gemeinsam-feststellen.md
  Entscheidungsmatrix-Besetzung-und-Planbarkeit.md
  Entscheidungsmatrix-Ausfall-und-Ersatzbesetzung.md
  Nutzung.md
  Nutzung-Grundbegriffe.md
  Nutzung-Pruefungshalbjahre.md
  Nutzung-Stammdaten.md
  Nutzung-Terminplanung.md
  Administration.md
  Administration-Lokale-Laufzeit.md
  Administration-Daten-und-Zuruecksetzen.md
  Entwicklung.md
  Entwicklung-Einrichtung.md
  Entwicklung-Arbeitsprozess.md
  Entwicklung-Qualitaet-und-Sicherheit.md
  Entwicklung-Architektur.md
  Entwicklung-Dokumentation.md
]
missing = required.reject { |path| wiki.page(path) }
abort("gollum: required page missing: #{missing.join(', ')}") unless missing.empty?
nested = pages.map(&:path).select { |path| path.include?("/") }
abort("gollum: nested pages are forbidden: #{nested.join(', ')}") unless nested.empty?

# Force Gollum to parse/render every page before the workflow's portable checks.
pages.each { |page| page.formatted_data }
puts "gollum wiki policy: ok (#{pages.length} pages)"
