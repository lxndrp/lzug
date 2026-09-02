package admincli

import "context"

func systemCommands() []Command {
	commands := []Command{}
	for _, action := range []string{"config", "status", "doctor"} {
		action := action
		description := map[string]string{
			"config": "Validate the runtime's secret-free configuration contract.",
			"status": "Inspect runtime identity and application readiness.",
			"doctor": "Run runtime, schema, persistence, storage, and readiness diagnostics.",
		}[action]
		command := Command{
			Path:           []string{"system", action},
			Summary:        description,
			Description:    description + " The backend receives no operator secrets or business data.",
			Examples:       []string{"lzug-admin --container lzug system " + action},
			Transport:      ContainerExecTransport,
			BackendCommand: action,
			LegacyForms:    []string{action},
			Output:         OutputSpec{Human: HumanDiagnostics, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints a secret-free status and check summary; JSON includes the validated diagnostic result.", ResultKeys: []string{"command", "status", "checks"}},
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
