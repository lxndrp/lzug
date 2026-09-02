package admincli

import (
	"context"
	"fmt"
)

func operationalCommands() []Command {
	return []Command{
		{
			Path:        []string{"upgrade", "apply"},
			Summary:     "Apply a release-bound upgrade.",
			Description: "Verify CLI and container release identity, create and verify a safety backup, and apply supported migrations in a maintenance container.",
			Examples: []string{
				"printf 'PRIVATE_KEY' | lzug-admin --container lzug-maintenance upgrade apply --force",
				"printf 'PRIVATE_KEY' | lzug-admin --container lzug-maintenance upgrade apply --confirm-irreversible --force",
			},
			Options: []OptionSpec{
				{Name: "confirm-irreversible", Summary: "Confirm pending irreversible migrations when the backend requires it.", Kind: BooleanOption, DangerZone: true, DefaultText: "false"},
			},
			Secrets: []SecretSpec{{Name: "recipient-private-key", Description: "Private recipient key read only from standard input.", Prompt: "Private recipient key", Input: SecretStdin}},
			Confirmation: ConfirmationSpec{
				Required: true,
				Prompt: func(_ Values, config EffectiveConfig) string {
					return fmt.Sprintf("Apply the verified release upgrade to maintenance container %q?", config.Container.Value)
				},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "upgrade",
			LegacyForms:    []string{"upgrade"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the validated lifecycle result.", ResultKeys: []string{"target", "backup", "phases", "readiness"}},
			BuildRequest: func(ctx context.Context, prepare PrepareContext, values, secrets Values) (BackendRequest, error) {
				target, err := prepare.ReleaseInspector.Target(ctx, prepare.Build)
				if err != nil {
					return BackendRequest{}, err
				}
				return BackendRequest{
					Version: ProtocolVersion,
					Command: "upgrade",
					Arguments: map[string]any{
						"recipient_private_key": secrets.String("recipient-private-key"),
						"confirm_irreversible":  values.Bool("confirm-irreversible"),
						"target":                target,
					},
				}, nil
			},
		},
		{
			Path:           []string{"upgrade", "rollback"},
			Summary:        "Inspect release-bound rollback eligibility.",
			Description:    "Verify CLI and container release identity and evaluate rollback eligibility without mutating the installation.",
			Examples:       []string{"lzug-admin --container lzug-maintenance upgrade rollback"},
			Transport:      ContainerExecTransport,
			BackendCommand: "rollback",
			LegacyForms:    []string{"rollback"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the validated rollback result.", ResultKeys: []string{"target", "eligible", "reason"}},
			BuildRequest: func(ctx context.Context, prepare PrepareContext, _, _ Values) (BackendRequest, error) {
				target, err := prepare.ReleaseInspector.Target(ctx, prepare.Build)
				if err != nil {
					return BackendRequest{}, err
				}
				return BackendRequest{Version: ProtocolVersion, Command: "rollback", Arguments: map[string]any{"target": target}}, nil
			},
		},
		{
			Path:           []string{"notification", "process"},
			Summary:        "Process due technical notifications.",
			Description:    "Process due notification deliveries and confirmed-plan consequences without returning message content.",
			Examples:       []string{"lzug-admin --container lzug notification process"},
			Transport:      ContainerExecTransport,
			BackendCommand: "process-notifications",
			LegacyForms:    []string{"process-notifications"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes technical counters only.", ResultKeys: []string{"processed", "succeeded", "failed", "plan_consequences"}},
			BuildRequest:   simpleRequest("process-notifications", func(_, _ Values) map[string]any { return map[string]any{} }),
		},
		{
			Path:        []string{"notification", "test"},
			Summary:     "Run one synthetic notification test.",
			Description: "Run a technical synthetic delivery for one committee member without returning message content.",
			Examples:    []string{"lzug-admin --container lzug notification test --member-id 7 --channel web_push"},
			Options: []OptionSpec{
				{Name: "member-id", ValueName: "ID", Summary: "Positive committee member identifier.", Kind: IntegerOption, Required: true, Positive: true},
				{Name: "channel", ValueName: "CHANNEL", Summary: "Notification channel.", Kind: StringOption, Required: true, Choices: []string{"web_push", "email"}},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "test-notification",
			LegacyForms:    []string{"test-notification"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes synthetic technical delivery details.", ResultKeys: []string{"notification_id", "deliveries"}},
			BuildRequest: simpleRequest("test-notification", func(values, _ Values) map[string]any {
				return map[string]any{"member_id": values.Int("member-id"), "channel": values.String("channel")}
			}),
		},
		planConsequenceCommand("status"),
		planConsequenceCommand("retry"),
	}
}

func planConsequenceCommand(action string) Command {
	backendCommand := "plan-consequences-status"
	legacy := backendCommand
	summary := "Inspect technical confirmed-plan consequences."
	description := "Inspect technical follow-up states for one confirmed plan revision without exposing business content."
	output := OutputSpec{Human: HumanPlanStatus, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints a technical status summary; JSON includes the validated technical result.", ResultKeys: []string{"revision_id", "technical_items"}}
	if action == "retry" {
		backendCommand = "retry-plan-consequences"
		legacy = backendCommand
		summary = "Retry technical confirmed-plan consequences."
		description = "Retry eligible technical follow-up work for one confirmed plan revision without exposing business content."
		output = OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes technical counters only.", ResultKeys: []string{"revision_id", "derivation_status", "processed", "problems", "pending", "superseded"}}
	}
	return Command{
		Path:           []string{"plan-consequence", action},
		Summary:        summary,
		Description:    description,
		Examples:       []string{fmt.Sprintf("lzug-admin --container lzug plan-consequence %s --revision-id 17", action)},
		Options:        []OptionSpec{{Name: "revision-id", ValueName: "ID", Summary: "Positive confirmed plan revision identifier.", Kind: IntegerOption, Required: true, Positive: true}},
		Transport:      ContainerExecTransport,
		BackendCommand: backendCommand,
		LegacyForms:    []string{legacy},
		Output:         output,
		BuildRequest: simpleRequest(backendCommand, func(values, _ Values) map[string]any {
			return map[string]any{"revision_id": values.Int("revision-id")}
		}),
	}
}
