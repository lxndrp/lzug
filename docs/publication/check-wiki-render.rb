# frozen_string_literal: true

# Render the complete flat candidate with the same Gollum library used by GitHub Wiki.
require "gollum-lib"

wiki_root = File.expand_path(ARGV.fetch(0))
wiki = Gollum::Wiki.new(wiki_root)
source_pages = Dir.glob(File.join(wiki_root, "*.md"))
                  .map { |path| File.basename(path) }
                  .reject { |name| name == "_Sidebar.md" }
                  .sort

abort("gollum: Wiki candidate has no content pages") if source_pages.empty?
missing = source_pages.reject { |name| wiki.page(name) }
abort("gollum: pages are not loadable: #{missing.join(', ')}") unless missing.empty?

source_pages.each do |name|
  page = wiki.page(name)
  rendered = page.formatted_data
  abort("gollum: page rendered empty: #{name}") if rendered.strip.empty?
end

puts "gollum Wiki candidate: ok (#{source_pages.length} rendered pages)"
