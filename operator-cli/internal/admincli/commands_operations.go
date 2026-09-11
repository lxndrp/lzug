package admincli

import (
	"context"
	"fmt"
	"io"
)

func operationalCommands() []Command {
	return []Command{
		upgradeApplyCommand(),
		upgradeInspectionCommand("status"),
		upgradeInspectionCommand("rollback"),
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

const rollbackBoundary = "No reverse migration is supported. Image changes belong to the container platform. After migration, restore a complete verified backup with a compatible image or use supported forward recovery."

func upgradeInspectionCommand(action string) Command {
	var options []OptionSpec
	if action == "status" {
		options = []OptionSpec{{Name: "job-id", ValueName: "UUID", Summary: "Inspect a prior socket job, including the last durable migration job after restart.", Kind: StringOption}}
	}
	return Command{
		Path:        []string{"upgrade", action},
		Summary:     map[string]string{"status": "Inspect the running backend's data migration plan.", "rollback": "Explain and reject unsupported automatic rollback."}[action],
		Description: "Read application and schema compatibility through the existing socket. " + rollbackBoundary,
		Examples:    []string{"lzug-admin --endpoint unix:///run/lzug-admin/admin.sock upgrade " + action},
		UsesConfig:  true, Transport: LocalTransport,
		Options:     options,
		LegacyForms: map[string][]string{"rollback": {"rollback"}}[action],
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Human and JSON output expose the migration plan and rollback boundary."},
		Local: func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
			if failure := requireMigrationSocket(local); failure != nil {
				return LocalResult{}, failure
			}
			command := "upgrade-status"
			arguments := map[string]any{}
			if id := values.String("job-id"); id != "" {
				if !socketID.MatchString(id) {
					return LocalResult{}, invalidInvocation("--job-id requires a valid job UUID")
				}
				command, arguments = "socket-job-status", map[string]any{"job_id": id}
			}
			if action == "rollback" {
				command = "rollback"
			}
			result, failure := callBackend(ctx, local, command, arguments)
			if failure != nil {
				return LocalResult{}, failure
			}
			if command == "socket-job-status" {
				return LocalResult{Result: result, HumanOutput: fmt.Sprintf("Job: %v. Status: %v.\n", result["job_id"], result["status"])}, nil
			}
			return LocalResult{Result: result, HumanOutput: migrationSummary(result)}, nil
		},
	}
}

func requireMigrationSocket(local LocalContext) *CLIError {
	// Keep the general legacy adapter for #747, but never reach it for upgrades.
	if local.Config.target("endpoint") == "" {
		return invalidInvocation("upgrade commands require --endpoint for the running backend; container-exec is not a migration transport")
	}
	return nil
}

func migrationSummary(result map[string]any) string {
	application, _ := result["application"].(map[string]any)
	migration, _ := result["migration"].(map[string]any)
	runtime, _ := result["runtime"].(map[string]any)
	return fmt.Sprintf("Application: %v. State: %v. Schema: %v -> %v. Pending: %v.\n%s\n", application["identity"], runtime["state"], migration["current"], migration["target"], migration["pending"], rollbackBoundary)
}

func upgradeApplyCommand() Command {
	return Command{
		Path:        []string{"upgrade", "apply"},
		Summary:     "Approve the running backend's data migration.",
		Description: "Inspect the plan, create and locally decrypt a protected backup, then explicitly approve the data transition in the same running backend. " + rollbackBoundary,
		Examples:    []string{"lzug-admin --endpoint unix:///run/lzug-admin/admin.sock upgrade apply --backup-output pre-upgrade.lzug --identity-file backup.agekey --confirm-irreversible --force"},
		Options: []OptionSpec{
			{Name: "backup-output", ValueName: "PATH", Summary: "New local protected pre-migration backup.", Kind: StringOption, Required: true},
			{Name: "identity-file", ValueName: "PATH", Summary: "Protected local age identity file.", Kind: StringOption},
			{Name: "identity-stdin", Summary: "Read the age identity from redirected standard input.", Kind: BooleanOption, DefaultText: "false"},
			{Name: "identity-prompt", Summary: "Read the age identity from a hidden terminal prompt.", Kind: BooleanOption, DefaultText: "false"},
			{Name: "confirm-irreversible", Summary: "Explicitly approve the data migration and restore-only rollback boundary; --force does not imply this.", Kind: BooleanOption, DangerZone: true, DefaultText: "false"},
		},
		Confirmation: ConfirmationSpec{Required: true, Deferred: true, Prompt: func(_ Values, _ EffectiveConfig) string {
			return "Approve the data migration in the running backend? " + rollbackBoundary
		}},
		UsesConfig: true, Transport: LocalTransport, LegacyForms: []string{"upgrade"},
		Output:   OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "JSON includes the runtime job ID and result. Lost connections never replay the migration."},
		Validate: validateIdentitySource,
		Local:    runUpgrade,
	}
}

func runUpgrade(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
	if failure := requireMigrationSocket(local); failure != nil {
		return LocalResult{}, failure
	}
	plan, failure := callBackend(ctx, local, "upgrade-status", map[string]any{})
	if failure != nil {
		return LocalResult{}, failure
	}
	planID, _ := plan["plan_id"].(string)
	if plan["supported"] != true || len(planID) != 64 {
		return LocalResult{}, artifactLocalError("schema_incompatible", "No supported pending data migration. Inspect upgrade status.", ExitSchemaIncompatible)
	}
	if !values.Bool("confirm-irreversible") {
		return LocalResult{}, invalidInvocation("--confirm-irreversible is required; --force does not approve irreversible migration. %s", rollbackBoundary)
	}
	if !local.Global.Force {
		if !local.Input.IsTerminal() {
			return LocalResult{}, invalidInvocation("upgrade apply requires interactive confirmation or --force. %s", rollbackBoundary)
		}
		confirmed, err := local.Input.Confirm("Target: " + local.Config.targetDescription() + "\n" + migrationSummary(plan) + "Create a verified backup and approve this data migration?")
		if err != nil {
			return LocalResult{}, interruptedError()
		}
		if !confirmed {
			return LocalResult{}, invalidInvocation("data migration was not approved")
		}
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
	recipient, configuredFingerprint, err := parseRecipient(recipientValue)
	if err != nil {
		return LocalResult{}, err.(*CLIError)
	}
	if configuredFingerprint != fingerprint {
		return LocalResult{}, artifactLocalError("recipient_key_mismatch", "The identity does not match the configured backup recipient.", ExitInvalidInvocation)
	}
	transport, failure := ensureArtifactTransport(local)
	if failure != nil {
		return LocalResult{}, failure
	}
	createRequest := BackendRequest{Command: "backup-package-create", Arguments: map[string]any{"recipient_key_fingerprint": fingerprint}}
	_, _, failure = writeProtectedArtifact(ctx, values.String("backup-output"), recipient, fingerprint, func(target io.Writer) (BackendResponse, int, error) {
		return transport.Produce(ctx, createRequest, target)
	})
	if failure != nil {
		return LocalResult{}, failure
	}
	verifyRequest := BackendRequest{Command: "artifact-package-verify", Arguments: map[string]any{"artifact_type": "backup"}}
	_, _, failure = consumeProtectedArtifact(values.String("backup-output"), identity, fingerprint, func(source io.Reader) (BackendResponse, int, error) {
		return transport.Consume(ctx, verifyRequest, source)
	})
	if failure != nil {
		return LocalResult{}, failure
	}
	request := BackendRequest{Command: "upgrade-package-apply", Arguments: map[string]any{
		"plan_id": planID, "recipient_key_fingerprint": fingerprint, "confirm_irreversible": true,
	}}
	response, _, failure := consumeProtectedArtifact(values.String("backup-output"), identity, fingerprint, func(source io.Reader) (BackendResponse, int, error) {
		return transport.Consume(ctx, request, source)
	})
	if failure != nil {
		return LocalResult{}, failure
	}
	result, failure := decodeBackendResult(response)
	if failure != nil {
		return LocalResult{}, failure
	}
	return LocalResult{Result: result, HumanOutput: fmt.Sprintf("Data migration completed. Job: %v.\n", result["job_id"])}, nil
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
