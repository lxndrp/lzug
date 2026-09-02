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
			Summary:     "Start the guided interactive operator dialog.",
			Description: "Start the line-oriented terminal dialog generated from this command registry. Interactive input and output terminals are required; --json and --force are invalid. Direct subcommands remain the interface for automation.",
			Examples:    []string{"lzug-admin cli"},
			Transport:   LocalTransport,
			Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Runs the guided terminal session until the operator exits or interrupts it."},
			Local: func(_ context.Context, _ LocalContext, _ Values) (LocalResult, *CLIError) {
				return LocalResult{}, &CLIError{
					Class:    "interactive_session_required",
					Message:  "The guided mode must be entered through the top-level cli invocation.",
					NextStep: "Run lzug-admin cli in an interactive terminal.",
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
