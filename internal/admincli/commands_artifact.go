package admincli

import (
	"context"
	"fmt"
	"io"
	"path/filepath"
	"strings"
	"time"
)

func artifactCommands() []Command {
	identityOptions := []OptionSpec{
		{Name: "identity-file", ValueName: "PATH", Summary: "Protected local age identity file.", Kind: StringOption},
		{Name: "identity-stdin", Summary: "Read the age identity from redirected standard input.", Kind: BooleanOption, DefaultText: "false"},
		{Name: "identity-prompt", Summary: "Read the age identity from a hidden terminal prompt.", Kind: BooleanOption, DefaultText: "false"},
	}
	artifact := OptionSpec{Name: "artifact", ValueName: "PATH", Summary: "Regular protected artifact file.", Kind: StringOption, Required: true}
	output := OptionSpec{Name: "output", ValueName: "PATH", Summary: "New protected target artifact file.", Kind: StringOption, Required: true}
	return []Command{
		recipientGenerateCommand(),
		recipientInspectCommand(),
		artifactInspectCommand(artifact),
		backupRecipientCommand("show", identityOptions),
		backupRecipientCommand("set", identityOptions),
		backupRecipientCommand("replace", identityOptions),
		artifactCreateCommand("backup", output),
		artifactVerifyCommand("backup", artifact, identityOptions),
		artifactRestoreCommand(artifact, identityOptions),
		artifactCreateCommand("export", output),
		artifactVerifyCommand("export", artifact, identityOptions),
	}
}

func recipientGenerateCommand() Command {
	return Command{
		Path:        []string{"recipient-key", "generate"},
		Summary:     "Generate a dedicated X25519 age recipient keypair.",
		Description: "Create a protected private identity and a shareable public recipient atomically without overwriting files.",
		Examples:    []string{"lzug-admin recipient-key generate --identity-file backup.agekey --recipient-file backup.agepub"},
		Options: []OptionSpec{
			{Name: "identity-file", ValueName: "PATH", Summary: "New private identity file.", Kind: StringOption, Required: true},
			{Name: "recipient-file", ValueName: "PATH", Summary: "New public recipient file.", Kind: StringOption, Required: true},
		},
		Transport: LocalTransport,
		Output:    OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Human output reminds about independent key backup; JSON excludes the private identity."},
		Local: func(_ context.Context, _ LocalContext, values Values) (LocalResult, *CLIError) {
			result, failure := generateRecipientKeypair(values.String("identity-file"), values.String("recipient-file"))
			if failure != nil {
				return LocalResult{}, failure
			}
			return LocalResult{Result: result, HumanOutput: "Private identity created. Store an independent copy away from the lzug host.\n"}, nil
		},
	}
}

func recipientInspectCommand() Command {
	return Command{
		Path:        []string{"recipient-key", "inspect"},
		Summary:     "Inspect a private identity or public recipient file.",
		Description: "Show only the canonical public recipient, method, and complete fingerprint.",
		Examples:    []string{"lzug-admin recipient-key inspect --key-file backup.agekey"},
		Options:     []OptionSpec{{Name: "key-file", ValueName: "PATH", Summary: "Private identity or public recipient file.", Kind: StringOption, Required: true}},
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Shows no private identity value."},
		Local: func(_ context.Context, _ LocalContext, values Values) (LocalResult, *CLIError) {
			result, failure := inspectKeyFile(values.String("key-file"))
			if failure != nil {
				return LocalResult{}, failure
			}
			return LocalResult{Result: result, HumanOutput: fmt.Sprintf("%s\n%s\n", result["recipient"], result["fingerprint"])}, nil
		},
	}
}

func artifactInspectCommand(artifact OptionSpec) Command {
	return Command{
		Path:        []string{"artifact", "inspect"},
		Summary:     "Inspect the public minimum artifact preamble.",
		Description: "Show format, protection method, and required fingerprint without an identity or business data.",
		Examples:    []string{"lzug-admin artifact inspect --artifact backup.lzug"},
		Options:     []OptionSpec{artifact},
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Shows only the public preamble."},
		Local: func(_ context.Context, _ LocalContext, values Values) (LocalResult, *CLIError) {
			result, failure := inspectArtifact(values.String("artifact"))
			if failure != nil {
				return LocalResult{}, failure
			}
			return LocalResult{Result: result, HumanOutput: fmt.Sprintf("%s %v\n%s\n", result["format"], result["format_version"], result["recipient_key_fingerprint"])}, nil
		},
	}
}

func backupRecipientCommand(action string, identityOptions []OptionSpec) Command {
	command := Command{
		Path:        []string{"backup", "recipient", action},
		Summary:     map[string]string{"show": "Show the active public backup recipient.", "set": "Set the first public backup recipient.", "replace": "Replace the active public backup recipient."}[action],
		Description: "Manage only the persistent public age recipient after local possession proof; private identities never reach the backend.",
		Examples:    []string{"lzug-admin --container lzug backup recipient " + action},
		UsesConfig:  true,
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Shows the canonical public recipient and complete fingerprint."},
	}
	if action != "show" {
		command.Options = append([]OptionSpec{}, identityOptions...)
		command.Validate = validateIdentitySource
		command.Examples[0] += " --identity-file backup.agekey"
	}
	if action == "replace" {
		command.Confirmation = ConfirmationSpec{Required: true, Deferred: true, Prompt: func(Values, EffectiveConfig) string { return "deferred" }}
	}
	command.Local = func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
		if action == "show" {
			result, failure := callBackend(ctx, local, "backup-recipient-show", map[string]any{})
			if failure != nil {
				return LocalResult{}, failure
			}
			return recipientResult(result), nil
		}
		identity, recipient, fingerprint, failure := loadIdentity(local.Input, values)
		if failure != nil {
			return LocalResult{}, failure
		}
		if identitySelfTest(identity) != nil {
			return LocalResult{}, artifactLocalError("recipient_self_test_failed", "Local recipient possession proof failed.", ExitUnexpected)
		}
		if action == "replace" {
			current, currentFailure := callBackend(ctx, local, "backup-recipient-show", map[string]any{})
			if currentFailure != nil {
				return LocalResult{}, currentFailure
			}
			if !local.Global.Force {
				if !local.Input.IsTerminal() {
					return LocalResult{}, invalidInvocation("backup recipient replace requires an interactive confirmation or --force")
				}
				prompt := fmt.Sprintf("Replace backup recipient %s with %s?", current["fingerprint"], fingerprint)
				confirmed, err := local.Input.Confirm(prompt)
				if err != nil || !confirmed {
					return LocalResult{}, artifactLocalError("confirmation_declined", "The recipient replacement was not confirmed.", ExitInvalidInvocation)
				}
			}
		}
		result, backendFailure := callBackend(ctx, local, "backup-recipient-"+action, map[string]any{"recipient": recipient, "fingerprint": fingerprint})
		if backendFailure != nil {
			return LocalResult{}, backendFailure
		}
		return recipientResult(result), nil
	}
	return command
}

func recipientResult(result map[string]any) LocalResult {
	return LocalResult{Result: result, HumanOutput: fmt.Sprintf("%s\n%s\n", result["recipient"], result["fingerprint"])}
}

func artifactCreateCommand(kind string, output OptionSpec) Command {
	isExport := kind == "export"
	options := []OptionSpec{output}
	if isExport {
		options = append(options, OptionSpec{Name: "recipient", ValueName: "AGE_RECIPIENT", Summary: "Explicit public X25519 age recipient.", Kind: StringOption, Required: true})
	}
	command := Command{
		Path:        []string{kind, "create"},
		Summary:     map[bool]string{false: "Create a protected full backup.", true: "Create a protected full export."}[isExport],
		Description: "Stream a backend-validated clear package directly into a local age-encrypted atomic target.",
		Examples:    []string{map[bool]string{false: "lzug-admin --container lzug backup create --output backup.lzug", true: "lzug-admin --container lzug export create --recipient age1... --output export.lzug --force"}[isExport]},
		Options:     options,
		UsesConfig:  true,
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Prints the activated local artifact path; JSON includes secret-free metadata."},
	}
	if isExport {
		command.LegacyForms = []string{"full-export"}
	} else {
		command.LegacyForms = []string{"backup-create"}
	}
	if isExport {
		command.Confirmation = ConfirmationSpec{Required: true, Prompt: func(values Values, _ EffectiveConfig) string {
			_, fingerprint, err := parseRecipient(values.String("recipient"))
			if err != nil {
				return "Confirm the explicitly supplied export recipient?"
			}
			return "Create a full export for " + fingerprint + "?"
		}}
	}
	command.Local = func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
		var recipientValue string
		if isExport {
			recipientValue = values.String("recipient")
		} else {
			configured, failure := callBackend(ctx, local, "backup-recipient-show", map[string]any{})
			if failure != nil {
				return LocalResult{}, failure
			}
			recipientValue, _ = configured["recipient"].(string)
		}
		recipient, fingerprint, parseErr := parseRecipient(recipientValue)
		if parseErr != nil {
			return LocalResult{}, parseErr.(*CLIError)
		}
		transport, failure := ensureArtifactTransport(local)
		if failure != nil {
			return LocalResult{}, failure
		}
		request := BackendRequest{Command: map[bool]string{false: "backup-package-create", true: "export-package-create"}[isExport], Arguments: map[string]any{"recipient_key_fingerprint": fingerprint}}
		response, _, localFailure := writeProtectedArtifact(ctx, values.String("output"), recipient, fingerprint, func(target io.Writer) (BackendResponse, int, error) {
			return transport.Produce(ctx, request, target)
		})
		if localFailure != nil {
			return LocalResult{}, localFailure
		}
		result, decodeFailure := decodeBackendResult(response)
		if decodeFailure != nil {
			return LocalResult{}, decodeFailure
		}
		result["artifact"] = values.String("output")
		return LocalResult{Result: result, HumanOutput: artifactHuman(result)}, nil
	}
	return command
}

func artifactVerifyCommand(kind string, artifact OptionSpec, identityOptions []OptionSpec) Command {
	options := append([]OptionSpec{artifact}, identityOptions...)
	return Command{
		Path:        []string{kind, "verify"},
		Summary:     "Verify a protected " + kind + " without mutation.",
		Description: "Decrypt locally and stream the clear package to the backend for complete validation.",
		Examples:    []string{"lzug-admin --container lzug " + kind + " verify --artifact " + kind + ".lzug --identity-file backup.agekey"},
		Options:     options,
		UsesConfig:  true,
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Human success is silent; JSON contains the validated backend report."},
		Validate:    validateIdentitySource,
		LegacyForms: []string{map[string]string{"backup": "artifact-verify (backup artifact)", "export": "artifact-verify (full-export artifact)"}[kind]},
		Local: func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
			identity, _, fingerprint, failure := loadIdentity(local.Input, values)
			if failure != nil {
				return LocalResult{}, failure
			}
			transport, failure := ensureArtifactTransport(local)
			if failure != nil {
				return LocalResult{}, failure
			}
			request := BackendRequest{Command: "artifact-package-verify", Arguments: map[string]any{"artifact_type": map[string]string{"backup": "backup", "export": "full_export"}[kind]}}
			response, _, localFailure := consumeProtectedArtifact(values.String("artifact"), identity, fingerprint, func(source io.Reader) (BackendResponse, int, error) {
				return transport.Consume(ctx, request, source)
			})
			if localFailure != nil {
				return LocalResult{}, localFailure
			}
			result, decodeFailure := decodeBackendResult(response)
			if decodeFailure != nil {
				return LocalResult{}, decodeFailure
			}
			result["artifact"] = values.String("artifact")
			return LocalResult{Result: result, HumanOutput: ""}, nil
		},
	}
}

func artifactRestoreCommand(artifact OptionSpec, identityOptions []OptionSpec) Command {
	options := []OptionSpec{
		artifact,
		{Name: "replace", Summary: "Replace a non-empty installation after creating a safety artifact.", Kind: BooleanOption, DangerZone: true, DefaultText: "false"},
	}
	options = append(options, identityOptions...)
	return Command{
		Path:        []string{"backup", "restore"},
		Summary:     "Restore a protected backup.",
		Description: "Decrypt locally, validate and stage in the backend, then activate only after every precheck succeeds.",
		Examples:    []string{"lzug-admin --container lzug backup restore --artifact backup.lzug --identity-file backup.agekey --force"},
		Options:     options,
		Confirmation: ConfirmationSpec{Required: true, Prompt: func(values Values, config EffectiveConfig) string {
			return fmt.Sprintf("Restore %q into container %q?", values.String("artifact"), config.Container.Value)
		}},
		UsesConfig:  true,
		Transport:   LocalTransport,
		Output:      OutputSpec{Human: HumanLocal, Verbose: VerboseSummary, JSON: JSONLocal, Summary: "Human success is silent; JSON includes restore phases and safety evidence."},
		Validate:    validateIdentitySource,
		LegacyForms: []string{"backup-restore"},
		Local: func(ctx context.Context, local LocalContext, values Values) (LocalResult, *CLIError) {
			identity, _, fingerprint, failure := loadIdentity(local.Input, values)
			if failure != nil {
				return LocalResult{}, failure
			}
			transport, failure := ensureArtifactTransport(local)
			if failure != nil {
				return LocalResult{}, failure
			}
			safety := ""
			if values.Bool("replace") {
				configured, backendFailure := callBackend(ctx, local, "backup-recipient-show", map[string]any{})
				if backendFailure != nil {
					return LocalResult{}, backendFailure
				}
				recipientValue, _ := configured["recipient"].(string)
				recipient, configuredFingerprint, parseErr := parseRecipient(recipientValue)
				if parseErr != nil {
					return LocalResult{}, parseErr.(*CLIError)
				}
				safety = filepath.Join(filepath.Dir(values.String("artifact")), fmt.Sprintf("pre-restore-%s.lzug", time.Now().UTC().Format("20060102t150405z")))
				request := BackendRequest{Command: "backup-package-create", Arguments: map[string]any{"recipient_key_fingerprint": configuredFingerprint}}
				response, _, localFailure := writeProtectedArtifact(ctx, safety, recipient, configuredFingerprint, func(target io.Writer) (BackendResponse, int, error) {
					return transport.Produce(ctx, request, target)
				})
				if localFailure != nil {
					return LocalResult{}, localFailure
				}
				if _, failure = decodeBackendResult(response); failure != nil {
					return LocalResult{}, failure
				}
			}
			request := BackendRequest{Command: "backup-package-restore", Arguments: map[string]any{"replace": values.Bool("replace"), "safety_artifact": nilIfEmpty(safety), "recipient_key_fingerprint": fingerprint}}
			response, _, localFailure := consumeProtectedArtifact(values.String("artifact"), identity, fingerprint, func(source io.Reader) (BackendResponse, int, error) {
				return transport.Consume(ctx, request, source)
			})
			if localFailure != nil {
				return LocalResult{}, localFailure
			}
			result, decodeFailure := decodeBackendResult(response)
			if decodeFailure != nil {
				return LocalResult{}, decodeFailure
			}
			result["artifact"] = values.String("artifact")
			return LocalResult{Result: result, HumanOutput: ""}, nil
		},
	}
}

func callBackend(ctx context.Context, local LocalContext, command string, arguments map[string]any) (map[string]any, *CLIError) {
	response, exitCode, err := local.Runtime.Transport(local.Config).Execute(ctx, BackendRequest{Version: ProtocolVersion, Command: command, Arguments: arguments})
	if err != nil {
		return nil, runtimeFailure(err)
	}
	if !response.OK {
		return nil, backendCLIError(response, exitCode)
	}
	return decodeBackendResult(response)
}

func nilIfEmpty(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

func validateIdentitySource(values Values) error {
	return requireExactlyOne(values, "identity-file", "identity-stdin", "identity-prompt")
}
