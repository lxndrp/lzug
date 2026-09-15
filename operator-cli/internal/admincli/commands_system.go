package admincli

import (
	"context"
	"time"
)

func systemCommands() []Command {
	commands := []Command{}
	for _, action := range []string{"config", "status", "doctor"} {
		action := action
		description := map[string]string{
			"config": "Inspect the selected runtime configuration through the admin endpoint.",
			"status": "Inspect live readiness and runtime identity through the admin endpoint.",
			"doctor": "Inspect live runtime and listener state through the admin endpoint.",
		}[action]
		command := Command{
			Path:        []string{"system", action},
			Interactive: InteractiveSpec{SearchTerms: []string{"system", "diagnose", "bereitschaft", "status"}}, Effect: ReadOnlyEffect, Retry: RetryAllowed, Timeout: 2 * time.Minute,
			Summary:        description,
			Description:    description + " Socket targets report live runtime and listener state without opening storage. The backend receives no operator secrets or business data.",
			Examples:       []string{"lzug-admin --endpoint unix:///run/lzug-admin/admin.sock system " + action},
			Transport:      ContainerExecTransport,
			BackendCommand: action,
			LegacyForms:    []string{action},
			Output:         OutputSpec{Human: HumanDiagnostics, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints a secret-free status and check summary; JSON includes the validated runtime and socket snapshot.", ResultKeys: []string{"runtime", "socket", "command", "status", "checks"}},
		}
		command.BuildRequest = func(_ context.Context, prepare PrepareContext, _, _ Values) (BackendRequest, error) {
			arguments := map[string]any{}
			if action != "config" {
				arguments["client"] = map[string]any{
					"identity": prepare.Build.Version,
					"revision": prepare.Build.Revision,
				}
			}
			return BackendRequest{Version: ProtocolVersion, Command: action, Arguments: arguments}, nil
		}
		commands = append(commands, command)
	}
	return commands
}
