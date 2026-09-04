package admincli

import (
	"context"
	"fmt"
)

func accountCommands() []Command {
	email := OptionSpec{Name: "email", ValueName: "EMAIL", Summary: "Account email address.", Kind: StringOption, Required: true}
	accountID := OptionSpec{Name: "account-id", ValueName: "ID", Summary: "Positive account identifier.", Kind: IntegerOption, Required: true, Positive: true}
	return []Command{
		{
			Path:           []string{"account", "bootstrap"},
			Summary:        "Create the first operator account.",
			Description:    "Bootstrap an empty installation and issue its one-time invitation token.",
			Examples:       []string{"lzug-admin --container lzug account bootstrap --email operator@example.invalid"},
			Options:        []OptionSpec{email},
			Transport:      ContainerExecTransport,
			BackendCommand: "bootstrap",
			LegacyForms:    []string{"bootstrap"},
			Output:         OutputSpec{Human: HumanToken, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the issued one-time token; JSON includes the validated backend result.", ResultKeys: []string{"account", "kind", "expires_at", "token"}},
			BuildRequest: simpleRequest("bootstrap", func(values, _ Values) map[string]any {
				return map[string]any{"email": values.String("email")}
			}),
		},
		{
			Path:           []string{"account", "invite"},
			Summary:        "Invite an operator account.",
			Description:    "Create or reuse an eligible account invitation and print its one-time token.",
			Examples:       []string{"lzug-admin --container lzug account invite --email member@example.invalid"},
			Options:        []OptionSpec{email},
			Transport:      ContainerExecTransport,
			BackendCommand: "invite",
			LegacyForms:    []string{"invite"},
			Output:         OutputSpec{Human: HumanToken, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the issued one-time token; JSON includes the validated backend result.", ResultKeys: []string{"account", "kind", "expires_at", "token"}},
			BuildRequest: simpleRequest("invite", func(values, _ Values) map[string]any {
				return map[string]any{"email": values.String("email")}
			}),
		},
		{
			Path:        []string{"account", "disable"},
			Summary:     "Disable an operator account.",
			Description: "Disable one account and revoke its active sessions.",
			Examples:    []string{"lzug-admin --container lzug account disable --account-id 7 --force"},
			Options:     []OptionSpec{accountID},
			Confirmation: ConfirmationSpec{
				Required: true,
				Prompt: func(values Values, _ EffectiveConfig) string {
					return fmt.Sprintf("Disable account %d and revoke all active sessions?", values.Int("account-id"))
				},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "disable",
			LegacyForms:    []string{"disable"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes account and revocation details.", ResultKeys: []string{"account", "revoked_sessions"}},
			BuildRequest: simpleRequest("disable", func(values, _ Values) map[string]any {
				return map[string]any{"account_id": values.Int("account-id")}
			}),
		},
		{
			Path:        []string{"account", "recover"},
			Summary:     "Issue account recovery credentials.",
			Description: "Select exactly one account by identifier or email and issue a one-time recovery token.",
			Examples: []string{
				"lzug-admin --container lzug account recover --account-id 7",
				"lzug-admin --container lzug account recover --email member@example.invalid",
			},
			Options: []OptionSpec{
				{Name: "account-id", ValueName: "ID", Summary: "Positive account identifier.", Kind: IntegerOption, Positive: true},
				{Name: "email", ValueName: "EMAIL", Summary: "Account email address.", Kind: StringOption},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "recover",
			LegacyForms:    []string{"recover"},
			Output:         OutputSpec{Human: HumanToken, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the issued one-time token; JSON includes the validated backend result.", ResultKeys: []string{"account", "kind", "expires_at", "token"}},
			Validate: func(values Values) error {
				return requireExactlyOne(values, "account-id", "email")
			},
			BuildRequest: simpleRequest("recover", func(values, _ Values) map[string]any {
				if values.Int("account-id") > 0 {
					return map[string]any{"account_id": values.Int("account-id")}
				}
				return map[string]any{"email": values.String("email")}
			}),
		},
		accountConsumeCommand("invitation"),
		accountConsumeCommand("recovery"),
	}
}

func accountConsumeCommand(kind string) Command {
	action := "consume-" + kind
	return Command{
		Path:           []string{"account", action},
		Summary:        fmt.Sprintf("Consume a one-time %s token.", kind),
		Description:    fmt.Sprintf("Read one %s token from standard input and consume it through the local administration boundary.", kind),
		Examples:       []string{fmt.Sprintf("printf 'TOKEN' | lzug-admin --container lzug account %s", action)},
		Secrets:        []SecretSpec{{Name: "token", Description: "One-time token read only from standard input.", Prompt: "One-time token", Input: SecretStdin}},
		Transport:      ContainerExecTransport,
		BackendCommand: action,
		LegacyForms:    []string{action},
		Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the account result.", ResultKeys: []string{"account"}},
		BuildRequest: simpleRequest(action, func(_ Values, secrets Values) map[string]any {
			return map[string]any{"token": secrets.String("token")}
		}),
	}
}

func simpleRequest(
	backendCommand string,
	arguments func(Values, Values) map[string]any,
) func(context.Context, PrepareContext, Values, Values) (BackendRequest, error) {
	return func(_ context.Context, _ PrepareContext, values, secrets Values) (BackendRequest, error) {
		return BackendRequest{
			Version:   ProtocolVersion,
			Command:   backendCommand,
			Arguments: arguments(values, secrets),
		}, nil
	}
}
