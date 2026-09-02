package admincli

import (
	"fmt"
	"strings"
)

func GlobalOptionSpecs() []OptionSpec {
	return []OptionSpec{
		{Name: "engine", ValueName: "ENGINE", Summary: "Container engine: auto, docker, or podman.", Kind: StringOption, Choices: []string{"auto", "docker", "podman"}, DefaultText: "auto"},
		{Name: "container", ValueName: "NAME", Summary: "Exact running container name.", Kind: StringOption},
		{Name: "config", ValueName: "FILE", Summary: "Read this explicit non-secret JSON configuration file.", Kind: StringOption},
		{Name: "no-config", Summary: "Do not read a configuration file.", Kind: BooleanOption},
		{Name: "json", Summary: "Write exactly one machine-readable result object to stdout.", Kind: BooleanOption},
		{Name: "verbose", Summary: "Write additional secret-free diagnostics to stderr.", Kind: BooleanOption},
		{Name: "force", Summary: "Skip an ordinary destructive-operation prompt.", Kind: BooleanOption},
	}
}

func Help(registry *Registry, target string) (string, bool) {
	switch target {
	case "", "root":
		return rootHelp(registry), true
	}
	if group, found := registry.Group(target); found {
		return groupHelp(registry, group), true
	}
	command, found := registry.byName[target]
	if !found {
		return "", false
	}
	return commandHelp(command), true
}

func rootHelp(registry *Registry) string {
	var output strings.Builder
	output.WriteString("lzug-admin - local administration for lzug\n\n")
	output.WriteString("Usage:\n")
	output.WriteString("  lzug-admin [global options] <object> <action> [options]\n")
	output.WriteString("  lzug-admin [global options] cli\n\n")
	output.WriteString("Objects:\n")
	for _, group := range registry.Groups() {
		fmt.Fprintf(&output, "  %-18s %s\n", group.Name, group.Summary)
	}
	if command, found := registry.Find([]string{"cli"}); found {
		fmt.Fprintf(&output, "  %-18s %s\n", command.Name(), command.Summary)
	}
	output.WriteString("\nGlobal options:\n")
	writeOptions(&output, GlobalOptionSpecs())
	output.WriteString("  --help             Show global or contextual help.\n")
	output.WriteString("  --version          Show the CLI version.\n")
	output.WriteString("  --build-metadata   Show canonical build metadata as JSON.\n")
	return output.String()
}

func groupHelp(registry *Registry, group CommandGroup) string {
	var output strings.Builder
	fmt.Fprintf(&output, "lzug-admin %s - %s\n\n", group.Name, group.Summary)
	output.WriteString(group.Description + "\n\n")
	output.WriteString("Usage:\n")
	fmt.Fprintf(&output, "  lzug-admin [global options] %s <action> [options]\n\n", group.Name)
	output.WriteString("Actions:\n")
	for _, command := range registry.CommandsInGroup(group.Name) {
		fmt.Fprintf(&output, "  %-18s %s\n", command.Path[1], command.Summary)
	}
	output.WriteString("\nGlobal options:\n")
	writeOptions(&output, GlobalOptionSpecs())
	output.WriteString("  --help             Show this help.\n")
	return output.String()
}

func commandHelp(command *Command) string {
	var output strings.Builder
	fmt.Fprintf(&output, "lzug-admin %s - %s\n\n", command.Name(), command.Summary)
	output.WriteString(command.Description + "\n\n")
	output.WriteString("Usage:\n")
	fmt.Fprintf(&output, "  lzug-admin [global options] %s", command.Name())
	for _, argument := range command.Arguments {
		if argument.Required {
			fmt.Fprintf(&output, " <%s>", strings.ToUpper(argument.Name))
		} else {
			fmt.Fprintf(&output, " [<%s>]", strings.ToUpper(argument.Name))
		}
	}
	for _, option := range command.Options {
		if option.Required {
			fmt.Fprintf(&output, " --%s", option.Name)
			if option.Kind != BooleanOption {
				fmt.Fprintf(&output, " %s", option.ValueName)
			}
		}
	}
	if len(command.Options) > 0 {
		output.WriteString(" [options]")
	}
	output.WriteString("\n")
	if len(command.Arguments) > 0 {
		output.WriteString("\nArguments:\n")
		for _, argument := range command.Arguments {
			detail := argument.Summary
			if len(argument.Choices) > 0 {
				detail += " Values: " + strings.Join(argument.Choices, ", ") + "."
			}
			if argument.Required {
				detail += " Required."
			}
			fmt.Fprintf(&output, "  %-24s %s\n", "<"+strings.ToUpper(argument.Name)+">", detail)
		}
	}
	if len(command.Options) > 0 {
		output.WriteString("\nCommand options:\n")
		writeOptions(&output, command.Options)
	}
	if len(command.Secrets) > 0 {
		output.WriteString("\nSecure input:\n")
		for _, secret := range command.Secrets {
			fmt.Fprintf(&output, "  %-18s %s\n", secret.Input, secret.Description)
		}
	}
	if command.Confirmation.Required {
		output.WriteString("\nConfirmation:\n")
		output.WriteString("  Requires an interactive terminal confirmation or --force.\n")
		for _, option := range command.Options {
			if option.DangerZone {
				fmt.Fprintf(&output, "  --%s is a separate danger-zone confirmation and is never implied by --force.\n", option.Name)
			}
		}
	}
	output.WriteString("\nTransport:\n")
	if command.Transport == LocalTransport {
		output.WriteString("  Local command; no container request is sent.\n")
	} else {
		output.WriteString("  Versioned request through the shared Docker/Podman container transport.\n")
	}
	output.WriteString("\nOutput:\n")
	output.WriteString("  " + command.Output.Summary + "\n")
	output.WriteString("  --verbose adds the secret-free progress and result summary on stderr.\n")
	output.WriteString("  --json uses the declared " + string(command.Output.JSON) + " result contract on stdout.\n")
	output.WriteString("\nExamples:\n")
	for _, example := range command.Examples {
		output.WriteString("  " + example + "\n")
	}
	return output.String()
}

func writeOptions(output *strings.Builder, options []OptionSpec) {
	for _, option := range options {
		label := "--" + option.Name
		if option.Kind != BooleanOption {
			label += " " + option.ValueName
		}
		detail := option.Summary
		if len(option.Choices) > 0 {
			detail += " Values: " + strings.Join(option.Choices, ", ") + "."
		}
		if option.DefaultText != "" {
			detail += " Default: " + option.DefaultText + "."
		}
		if option.Required {
			detail += " Required."
		}
		if option.DangerZone {
			detail += " Danger-zone confirmation."
		}
		fmt.Fprintf(output, "  %-24s %s\n", label, detail)
	}
}

func compact(values []string) []string {
	if len(values) == 0 {
		return values
	}
	result := values[:1]
	for _, value := range values[1:] {
		if value != result[len(result)-1] {
			result = append(result, value)
		}
	}
	return result
}
