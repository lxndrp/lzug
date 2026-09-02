package admincli

import (
	"context"
	"fmt"
)

func localCommands() []Command {
	commands := []Command{
		{
			Path:        []string{"config", "inspect"},
			Summary:     "Inspect effective non-secret CLI configuration.",
			Description: "Show the effective engine and container together with their flag, environment, file, or default source. No configuration is changed.",
			Examples: []string{
				"lzug-admin config inspect",
				"lzug-admin --no-config --engine podman --container lzug config inspect --json",
			},
			UsesConfig: true,
			Transport:  LocalTransport,
			Output:     OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Prints effective non-secret values and their source; JSON exposes the same fields.", ResultKeys: []string{"engine", "container"}},
			Local: func(_ context.Context, local LocalContext, _ Values) (LocalResult, *CLIError) {
				container := local.Config.Container.Value
				if container == "" {
					container = "<unset>"
				}
				return LocalResult{
					Result: local.Config,
					HumanOutput: fmt.Sprintf(
						"engine: %s (%s)\ncontainer: %s (%s)\n",
						local.Config.Engine.Value,
						local.Config.Engine.Source,
						container,
						local.Config.Container.Source,
					),
				}, nil
			},
		},
		{
			Path:        []string{"cli"},
			Summary:     "Start the guided interactive mode (reserved).",
			Description: "The registry entry reserves the shared interactive entry point for issue #570; this release does not implement an interactive user interface.",
			Examples:    []string{"lzug-admin cli"},
			Transport:   LocalTransport,
			Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Returns a stable unavailable-command error until the interactive mode is implemented."},
			Local: func(_ context.Context, _ LocalContext, _ Values) (LocalResult, *CLIError) {
				return LocalResult{}, &CLIError{
					Class:    "interactive_mode_unavailable",
					Message:  "The guided interactive mode is not available in this release.",
					NextStep: "Invoke a registered object and action directly.",
					ExitCode: ExitInvalidInvocation,
				}
			},
		},
	}
	for _, shell := range []string{"bash", "fish", "powershell", "zsh"} {
		shell := shell
		commands = append(commands, Command{
			Path:        []string{"completion", shell},
			Summary:     fmt.Sprintf("Generate %s completion.", shell),
			Description: fmt.Sprintf("Print an installable %s completion script derived only from static registry metadata.", shell),
			Examples:    []string{fmt.Sprintf("lzug-admin completion %s > lzug-admin.%s", shell, completionExtension(shell))},
			Transport:   LocalTransport,
			Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Prints the generated script; JSON returns the script as a string."},
			Local: func(_ context.Context, local LocalContext, _ Values) (LocalResult, *CLIError) {
				script, err := GenerateCompletion(local.Registry, shell)
				if err != nil {
					return LocalResult{}, unexpectedError()
				}
				return LocalResult{
					Result:      map[string]any{"shell": shell, "script": script},
					HumanOutput: script,
				}, nil
			},
		})
	}
	return commands
}

func completionExtension(shell string) string {
	switch shell {
	case "powershell":
		return "ps1"
	case "fish":
		return "fish"
	case "zsh":
		return "zsh"
	default:
		return "bash"
	}
}
