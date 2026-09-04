package admincli

import (
	"context"
	"fmt"
	"io"
)

func operationalCommands() []Command {
	return []Command{
		upgradeApplyCommand(),
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

func upgradeApplyCommand() Command {
	return Command{
		Path:        []string{"upgrade", "apply"},
		Summary:     "Apply a release-bound upgrade.",
		Description: "Create and locally decrypt a protected safety backup before applying supported migrations in a maintenance container.",
		Examples: []string{
			"lzug-admin --container lzug-maintenance upgrade apply --backup-output pre-upgrade.lzug --identity-file backup.agekey --force",
		},
		Options: []OptionSpec{
			{Name: "backup-output", ValueName: "PATH", Summary: "New local protected pre-upgrade backup.", Kind: StringOption, Required: true},
			{Name: "identity-file", ValueName: "PATH", Summary: "Protected local age identity file.", Kind: StringOption},
			{Name: "identity-stdin", Summary: "Read the age identity from redirected standard input.", Kind: BooleanOption, DefaultText: "false"},
			{Name: "identity-prompt", Summary: "Read the age identity from a hidden terminal prompt.", Kind: BooleanOption, DefaultText: "false"},
			{Name: "confirm-irreversible", Summary: "Confirm pending irreversible migrations when the backend requires it.", Kind: BooleanOption, DangerZone: true, DefaultText: "false"},
		},
		Confirmation: ConfirmationSpec{Required: true, Prompt: func(_ Values, config EffectiveConfig) string {
			return fmt.Sprintf("Apply the verified release upgrade to maintenance container %q?", config.Container.Value)
		}},
		UsesConfig:  true,
		Transport:   LocalTransport,
		LegacyForms: []string{"upgrade"},
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Successful human output is silent; JSON includes the validated lifecycle result."},
		Validate:    validateIdentitySource,
		Local: func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
			target, err := local.Runtime.ReleaseInspector(local.Config).Target(ctx, local.Build)
			if err != nil {
				return LocalResult{}, runtimeFailure(err)
			}
			identity, _, fingerprint, failure := loadIdentity(local.Input, values)
			if failure != nil {
				return LocalResult{}, failure
			}
			configured, failure := callBackend(ctx, local, "backup-recipient-show", map[string]any{})
			if failure != nil {
				return LocalResult{}, failure
			}
			recipientValue, _ := configured["recipient"].(string)
			recipient, configuredFingerprint, parseErr := parseRecipient(recipientValue)
			if parseErr != nil {
				return LocalResult{}, parseErr.(*CLIError)
			}
			if configuredFingerprint != fingerprint {
				return LocalResult{}, artifactLocalError("recipient_key_mismatch", "The identity does not match the configured backup recipient.", ExitInvalidInvocation)
			}
			transport, failure := ensureArtifactTransport(local)
			if failure != nil {
				return LocalResult{}, failure
			}
			createRequest := BackendRequest{Command: "backup-package-create", Arguments: map[string]any{"recipient_key_fingerprint": fingerprint}}
			created, _, localFailure := writeProtectedArtifact(ctx, values.String("backup-output"), recipient, fingerprint, func(target io.Writer) (BackendResponse, int, error) {
				return transport.Produce(ctx, createRequest, target)
			})
			if localFailure != nil {
				return LocalResult{}, localFailure
			}
			createdResult, failure := decodeBackendResult(created)
			if failure != nil {
				return LocalResult{}, failure
			}
			verifyRequest := BackendRequest{Command: "artifact-package-verify", Arguments: map[string]any{"artifact_type": "backup"}}
			verified, _, localFailure := consumeProtectedArtifact(values.String("backup-output"), identity, fingerprint, func(source io.Reader) (BackendResponse, int, error) {
				return transport.Consume(ctx, verifyRequest, source)
			})
			if localFailure != nil {
				return LocalResult{}, localFailure
			}
			backup, failure := decodeBackendResult(verified)
			if failure != nil {
				return LocalResult{}, failure
			}
			backup["artifact"] = values.String("backup-output")
			backup["artifact_id"] = createdResult["artifact_id"]
			backup["recipient_key_fingerprint"] = fingerprint
			backup["protection"] = artifactProtection
			backup["verified"] = true
			result, failure := callBackend(ctx, local, "upgrade", map[string]any{
				"target":               target,
				"backup":               backup,
				"confirm_irreversible": values.Bool("confirm-irreversible"),
			})
			if failure != nil {
				return LocalResult{}, failure
			}
			return LocalResult{Result: result, HumanOutput: ""}, nil
		},
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
