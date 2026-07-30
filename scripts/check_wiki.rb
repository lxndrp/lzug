# frozen_string_literal: true

# Load the published GitHub Wiki through the same Gollum library that renders it.
# The workflow supplies Gollum in an isolated, pinned container; it is not a
# dependency of the lzug Python/npm project.
require "gollum-lib"

wiki_root = ARGV.fetch(0)
wiki = Gollum::Wiki.new(wiki_root)
pages = wiki.pages
required = [
  "Home.md",
  "Fachlichkeit/index.md",
  "Nutzung/index.md",
  "Administration/index.md",
  "Entwicklung/index.md",
]
missing = required.reject { |path| wiki.page(path) }
abort("gollum: required page missing: #{missing.join(', ')}") unless missing.empty?
abort("gollum: required _Sidebar.md is missing") unless File.file?(File.join(wiki_root, "_Sidebar.md"))

# Force Gollum to parse/render every page before the workflow's portable checks.
pages.each { |page| page.formatted_data }
puts "gollum wiki policy: ok (#{pages.length} pages)"
