package admincli

import (
	"fmt"
	"regexp"
)

var artifactNamePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{0,180}\.lzug$`)

func artifactCommands() []Command {
	artifact := OptionSpec{Name: "artifact", ValueName: "NAME", Summary: "Protected artifact name inside the application data area.", Kind: StringOption, Required: true}
	privateKey := SecretSpec{Name: "recipient-private-key", Description: "Private recipient key read only from standard input.", Prompt: "Private recipient key", Input: SecretStdin}
	return []Command{
		{
			Path:           []string{"backup", "create"},
			Summary:        "Create a protected full backup.",
			Description:    "Create a consistent protected backup through the versioned local administration boundary.",
			Examples:       []string{"lzug-admin --container lzug backup create"},
			Transport:      ContainerExecTransport,
			BackendCommand: "backup-create",
			LegacyForms:    []string{"backup-create"},
			Output:         OutputSpec{Human: HumanArtifact, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the created artifact name; JSON includes the validated artifact result.", ResultKeys: artifactResultKeys()},
			BuildRequest:   simpleRequest("backup-create", func(_, _ Values) map[string]any { return map[string]any{} }),
		},
		{
			Path:           []string{"backup", "verify"},
			Summary:        "Verify a protected backup without mutation.",
			Description:    "Verify integrity, decryptability, and backup structure without changing the installation.",
			Examples:       []string{"printf 'PRIVATE_KEY' | lzug-admin --container lzug backup verify --artifact backup.lzug"},
			Options:        []OptionSpec{artifact},
			Secrets:        []SecretSpec{privateKey},
			Transport:      ContainerExecTransport,
			BackendCommand: "artifact-verify",
			LegacyForms:    []string{"artifact-verify (backup artifact)"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the validated verification result.", ResultKeys: artifactVerificationKeys()},
			Validate:       validateArtifactName,
			BuildRequest: simpleRequest("artifact-verify", func(values, secrets Values) map[string]any {
				return map[string]any{"artifact": values.String("artifact"), "recipient_private_key": secrets.String("recipient-private-key")}
			}),
		},
		{
			Path:        []string{"backup", "restore"},
			Summary:     "Restore a protected backup.",
			Description: "Restore a complete protected backup after validation. Replacing non-empty state also requires --replace.",
			Examples: []string{
				"printf 'PRIVATE_KEY' | lzug-admin --container lzug backup restore --artifact backup.lzug --force",
				"printf 'PRIVATE_KEY' | lzug-admin --container lzug backup restore --artifact backup.lzug --replace --force",
			},
			Options: []OptionSpec{
				artifact,
				{Name: "replace", Summary: "Confirm replacement of a non-empty installation.", Kind: BooleanOption, DangerZone: true, DefaultText: "false"},
			},
			Secrets: []SecretSpec{privateKey},
			Confirmation: ConfirmationSpec{
				Required: true,
				Prompt: func(values Values, config EffectiveConfig) string {
					return fmt.Sprintf(
						"Restore backup %q into container %q and replace its active application state?",
						values.String("artifact"),
						config.Container.Value,
					)
				},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "backup-restore",
			LegacyForms:    []string{"backup-restore"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the validated restore result.", ResultKeys: []string{"artifact", "artifact_type", "artifact_id", "snapshot_at", "safety_artifact", "phases", "readiness"}},
			Validate:       validateArtifactName,
			BuildRequest: simpleRequest("backup-restore", func(values, secrets Values) map[string]any {
				return map[string]any{
					"artifact":              values.String("artifact"),
					"recipient_private_key": secrets.String("recipient-private-key"),
					"replace":               values.Bool("replace"),
				}
			}),
		},
		{
			Path:        []string{"export", "create"},
			Summary:     "Create a protected full export.",
			Description: "Create a protected full export for an explicitly supplied public recipient key.",
			Examples:    []string{"lzug-admin --container lzug export create --recipient-public-key PUBLIC_KEY"},
			Options: []OptionSpec{
				{Name: "recipient-public-key", ValueName: "KEY", Summary: "Public recipient key for the protected export.", Kind: StringOption, Required: true},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "full-export",
			LegacyForms:    []string{"full-export"},
			Output:         OutputSpec{Human: HumanArtifact, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the created artifact name; JSON includes the validated artifact result.", ResultKeys: artifactResultKeys()},
			BuildRequest: simpleRequest("full-export", func(values, _ Values) map[string]any {
				return map[string]any{"recipient_public_key": values.String("recipient-public-key")}
			}),
		},
		{
			Path:           []string{"export", "verify"},
			Summary:        "Verify a protected full export without mutation.",
			Description:    "Verify integrity, decryptability, and full-export structure without changing the installation.",
			Examples:       []string{"printf 'PRIVATE_KEY' | lzug-admin --container lzug export verify --artifact export.lzug"},
			Options:        []OptionSpec{artifact},
			Secrets:        []SecretSpec{privateKey},
			Transport:      ContainerExecTransport,
			BackendCommand: "artifact-verify",
			LegacyForms:    []string{"artifact-verify (full-export artifact)"},
			Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the validated verification result.", ResultKeys: artifactVerificationKeys()},
			Validate:       validateArtifactName,
			BuildRequest: simpleRequest("artifact-verify", func(values, secrets Values) map[string]any {
				return map[string]any{"artifact": values.String("artifact"), "recipient_private_key": secrets.String("recipient-private-key")}
			}),
		},
	}
}

func validateArtifactName(values Values) error {
	if !artifactNamePattern.MatchString(values.String("artifact")) {
		return fmt.Errorf("--artifact must be a protected .lzug artifact name")
	}
	return nil
}

func artifactResultKeys() []string {
	return []string{"artifact", "artifact_type", "artifact_id", "snapshot_at", "manifest_version"}
}

func artifactVerificationKeys() []string {
	return []string{"artifact", "artifact_type", "artifact_id", "snapshot_at", "documents", "database", "manifest_version"}
}
