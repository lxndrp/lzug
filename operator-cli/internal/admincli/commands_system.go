package admincli

import "context"

func systemCommands() []Command {
	commands := []Command{}
	for _, action := range []string{"config", "status", "doctor"} {
		action := action
		description := map[string]string{
			"config": "Inspect the live runtime, or validate legacy runtime configuration.",
			"status": "Inspect live readiness, or legacy runtime identity and health checks.",
			"doctor": "Inspect live runtime and listener state, or legacy storage diagnostics.",
		}[action]
		command := Command{
			Path:           []string{"system", action},
			Summary:        description,
			Description:    description + " Socket targets report live runtime and listener state without opening storage. The backend receives no operator secrets or business data.",
			Examples:       []string{"lzug-admin --endpoint unix:///run/lzug-admin/admin.sock system " + action},
			Transport:      ContainerExecTransport,
			BackendCommand: action,
			LegacyForms:    []string{action},
			Output:         OutputSpec{Human: HumanDiagnostics, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints a secret-free status and check summary; JSON includes the validated runtime/socket snapshot or legacy diagnostic checks.", ResultKeys: []string{"runtime", "socket", "command", "status", "checks"}},
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
