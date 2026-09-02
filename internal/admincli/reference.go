package admincli

import (
	"fmt"
	"sort"
	"strings"
)

func GenerateReference(registry *Registry) string {
	var output strings.Builder
	output.WriteString("# `lzug-admin`-Befehlsreferenz\n\n")
	output.WriteString("<!-- Generated from internal/admincli registry metadata. Do not edit directly. -->\n\n")
	output.WriteString("Diese technische Referenz wird aus derselben statischen Registry wie Hilfe und Completion erzeugt.\n")
	output.WriteString("Die handgeschriebenen Betriebsabläufe bleiben im Administrationshandbuch.\n\n")
	output.WriteString("## Globale Optionen\n\n")
	output.WriteString("| Option | Bedeutung | Werte/Standard |\n")
	output.WriteString("| --- | --- | --- |\n")
	for _, option := range GlobalOptionSpecs() {
		values := "-"
		if len(option.Choices) > 0 {
			values = strings.Join(option.Choices, ", ")
		}
		if option.DefaultText != "" {
			if values == "-" {
				values = option.DefaultText
			} else {
				values += "; Standard: " + option.DefaultText
			}
		}
		fmt.Fprintf(&output, "| `%s` | %s | %s |\n", referenceOption(option), escapeTable(option.Summary), escapeTable(values))
	}
	output.WriteString("| `--help` | Globale oder kontextbezogene Hilfe ausgeben. | - |\n")
	output.WriteString("| `--version` | CLI-Version ausgeben. | - |\n")
	output.WriteString("| `--build-metadata` | Kanonische Build-Metadaten als JSON ausgeben. | - |\n\n")
	output.WriteString("Konfigurierbar sind nur Engine und Containername.\n")
	output.WriteString("Die Priorität lautet Flag vor Umgebungsvariable vor optionaler JSON-Datei vor Standardwert.\n\n")
	output.WriteString("## Konfiguration und sichere Eingabe\n\n")
	output.WriteString("Die Umgebungsvariablen `LZUG_ADMIN_ENGINE` und `LZUG_ADMIN_CONTAINER` sind die einzigen von der CLI ausgewerteten Konfigurationswerte.\n")
	output.WriteString("Ohne `--config` sucht die CLI plattformgerecht unter dem durch `os.UserConfigDir` bestimmten Verzeichnis nach `lzug/admin.json`; eine fehlende Standarddatei ist zulässig.\n")
	output.WriteString("Eine explizite fehlende oder ungültige Datei ist ein Konfigurationsfehler, und `--no-config` unterbindet jeden Dateizugriff.\n\n")
	output.WriteString("```json\n")
	output.WriteString("{\"engine\":\"podman\",\"container\":\"lzug\"}\n")
	output.WriteString("```\n\n")
	output.WriteString("Andere Dateischlüssel sowie Umgebungsvariablen für Secrets, Bestätigungen oder Ausgabepräferenzen werden abgewiesen.\n")
	output.WriteString("Einmaltoken und private Empfängerschlüssel besitzen keine CLI-Option und werden ausschließlich als einzelne Eingabe über `stdin` gelesen; am TTY bleibt die Eingabe ohne Echo.\n\n")
	output.WriteString("## Ausgabe, Fehler und Bestätigung\n\n")
	output.WriteString("Human-Ausgabe ist der Standard und bleibt bei einem vollständig spezifizierten erfolgreichen Vorgang grundsätzlich leer.\n")
	output.WriteString("Erforderliche Einmalwerte und ausdrücklich abgefragte Diagnose erscheinen auf `stdout`; Fehler, Warnungen, Rückfragen und `--verbose`-Diagnose erscheinen auf `stderr`.\n")
	output.WriteString("`--json` liefert bei Erfolg und Fehler genau ein Objekt mit `schema_version`, `protocol_version`, `ok`, `exit_code`, `command` und einem zulässigen `result` oder `error`.\n")
	output.WriteString("Rohe Engine-Ausgabe, interne Backendtexte und nicht deklarierte Ergebnisfelder werden nicht weitergereicht.\n\n")
	output.WriteString("| Exit Code | Bedeutung |\n")
	output.WriteString("| --- | --- |\n")
	output.WriteString("| `0` | Erfolg |\n")
	output.WriteString("| `1` | Unerwarteter lokaler Fehler |\n")
	output.WriteString("| `2` | Ungültiger Aufruf oder ungültige CLI-Eingabe |\n")
	output.WriteString("| `10-19` | Lokale Umgebung oder Transport |\n")
	output.WriteString("| `20-39` | Kontrollierter Backend-, Sicherheits-, Betriebs- oder Fachkonflikt |\n")
	output.WriteString("| `40-49` | Versions- oder Protokollinkompatibilität |\n")
	output.WriteString("| `130` | Abbruch durch `Ctrl+C` |\n\n")
	output.WriteString("Gewöhnlich destruktive Commands fragen an einem TTY konkret nach und benötigen ohne TTY `--force`.\n")
	output.WriteString("Als Danger Zone markierte semantische Flags bleiben davon unabhängig und werden durch `--force`, `--json` oder `--verbose` nie gesetzt.\n\n")
	output.WriteString("## Commands\n\n")
	for _, command := range registry.Commands() {
		fmt.Fprintf(&output, "### `lzug-admin %s`\n\n", command.Name())
		output.WriteString(command.Description + "\n\n")
		if len(command.Arguments) > 0 {
			output.WriteString("| Argument | Bedeutung | Pflicht/Werte |\n")
			output.WriteString("| --- | --- | --- |\n")
			for _, argument := range command.Arguments {
				requirement := "optional"
				if argument.Required {
					requirement = "Pflicht"
				}
				if len(argument.Choices) > 0 {
					requirement += "; Werte: " + strings.Join(argument.Choices, ", ")
				}
				fmt.Fprintf(&output, "| `<%s>` | %s | %s |\n", strings.ToUpper(argument.Name), escapeTable(argument.Summary), escapeTable(requirement))
			}
			output.WriteByte('\n')
		}
		if len(command.Options) > 0 {
			output.WriteString("| Option | Bedeutung | Pflicht/Standard |\n")
			output.WriteString("| --- | --- | --- |\n")
			for _, option := range command.Options {
				requirement := "optional"
				if option.Required {
					requirement = "Pflicht"
				}
				if option.DefaultText != "" {
					requirement += "; Standard: " + option.DefaultText
				}
				if option.DangerZone {
					requirement += "; separate Danger-Zone-Bestätigung"
				}
				fmt.Fprintf(&output, "| `%s` | %s | %s |\n", referenceOption(option), escapeTable(option.Summary), escapeTable(requirement))
			}
			output.WriteByte('\n')
		}
		if len(command.Secrets) > 0 {
			for _, secret := range command.Secrets {
				fmt.Fprintf(&output, "Sichere Eingabe: %s\n", secret.Description)
			}
			output.WriteByte('\n')
		}
		if command.Confirmation.Required {
			output.WriteString("Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.\n\n")
		}
		if command.Transport == LocalTransport {
			output.WriteString("Transport: lokale Ausführung ohne Container-Auftrag.\n\n")
		} else {
			output.WriteString("Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.\n\n")
		}
		output.WriteString("Ausgabe: " + command.Output.Summary + "\n")
		output.WriteString("`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `" + string(command.Output.JSON) + "`-Ergebnisvertrag auf `stdout`.\n\n")
		output.WriteString("```console\n")
		for _, example := range command.Examples {
			output.WriteString(example + "\n")
		}
		output.WriteString("```\n\n")
	}
	output.WriteString("## Migration der alten Syntax\n\n")
	output.WriteString("Die alten flachen Formen sind keine Aliase und werden als ungültiger Aufruf abgewiesen.\n\n")
	output.WriteString("| Alte Form bis v0.6.x | Neue Form ab v0.7.0 |\n")
	output.WriteString("| --- | --- |\n")
	for _, row := range migrationRows(registry) {
		fmt.Fprintf(&output, "| `%s` | `lzug-admin %s` |\n", escapeTable(row.old), escapeTable(row.current))
	}
	return output.String()
}

type migrationRow struct {
	old     string
	current string
}

func migrationRows(registry *Registry) []migrationRow {
	rows := []migrationRow{}
	for _, command := range registry.Commands() {
		for _, old := range command.LegacyForms {
			rows = append(rows, migrationRow{old: "lzug-admin " + old, current: command.Name()})
		}
	}
	sort.Slice(rows, func(left, right int) bool { return rows[left].old < rows[right].old })
	return rows
}

func referenceOption(option OptionSpec) string {
	label := "--" + option.Name
	if option.Kind != BooleanOption {
		label += " " + option.ValueName
	}
	return label
}

func escapeTable(value string) string {
	return strings.ReplaceAll(value, "|", "\\|")
}
