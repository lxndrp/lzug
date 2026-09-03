package admincli

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"regexp"
	"sort"
	"strings"

	"golang.org/x/term"
)

var publicErrorTokenPattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`)

type publicError struct {
	Class    string         `json:"class"`
	Message  string         `json:"message"`
	NextStep string         `json:"next_step,omitempty"`
	Phase    string         `json:"phase,omitempty"`
	Details  map[string]any `json:"details,omitempty"`
}

type outputEnvelope struct {
	SchemaVersion   int          `json:"schema_version"`
	ProtocolVersion int          `json:"protocol_version"`
	OK              bool         `json:"ok"`
	ExitCode        int          `json:"exit_code"`
	Command         string       `json:"command,omitempty"`
	Result          any          `json:"result,omitempty"`
	Error           *publicError `json:"error,omitempty"`
}

type OutputRenderer struct {
	stdout         io.Writer
	stderr         io.Writer
	outputTerminal bool
}

func NewOutputRenderer(stdout, stderr io.Writer) *OutputRenderer {
	terminal := false
	if file, ok := stdout.(*os.File); ok {
		terminal = term.IsTerminal(int(file.Fd()))
	}
	return &OutputRenderer{stdout: stdout, stderr: stderr, outputTerminal: terminal}
}

func (renderer *OutputRenderer) IsTerminal() bool {
	return renderer.outputTerminal
}

func (renderer *OutputRenderer) Dialog(text string) error {
	_, err := io.WriteString(renderer.stdout, text)
	return err
}

func (renderer *OutputRenderer) Error(global GlobalOptions, command string, failure *CLIError) {
	if global.JSON {
		_ = json.NewEncoder(renderer.stdout).Encode(outputEnvelope{
			SchemaVersion:   SchemaVersion,
			ProtocolVersion: ProtocolVersion,
			OK:              false,
			ExitCode:        failure.ExitCode,
			Command:         command,
			Error: &publicError{
				Class:    failure.Class,
				Message:  failure.Message,
				NextStep: failure.NextStep,
				Phase:    failure.Phase,
				Details:  failure.Details,
			},
		})
		return
	}
	_, _ = fmt.Fprintf(renderer.stderr, "Error [%s]: %s\n", failure.Class, failure.Message)
	if failure.NextStep != "" {
		_, _ = fmt.Fprintf(renderer.stderr, "Next: %s\n", failure.NextStep)
	}
}

func (renderer *OutputRenderer) Informational(global GlobalOptions, result any, human string) *CLIError {
	if global.JSON {
		if err := json.NewEncoder(renderer.stdout).Encode(outputEnvelope{
			SchemaVersion:   SchemaVersion,
			ProtocolVersion: ProtocolVersion,
			OK:              true,
			ExitCode:        ExitOK,
			Result:          result,
		}); err != nil {
			return unexpectedError()
		}
		return nil
	}
	if _, err := fmt.Fprint(renderer.stdout, human); err != nil {
		return unexpectedError()
	}
	return nil
}

func (renderer *OutputRenderer) Progress(global GlobalOptions, command *Command, phase string, exitCode int) {
	if !global.Verbose || command.Output.Verbose != VerboseSummary {
		return
	}
	if phase == "executing" {
		_, _ = fmt.Fprintf(renderer.stderr, "Executing %s.\n", command.Name())
		return
	}
	_, _ = fmt.Fprintf(renderer.stderr, "Completed %s with exit code %d. %s\n", command.Name(), exitCode, command.Output.Summary)
}

func (renderer *OutputRenderer) LocalSuccess(global GlobalOptions, command *Command, result LocalResult) *CLIError {
	if global.JSON {
		if err := json.NewEncoder(renderer.stdout).Encode(outputEnvelope{
			SchemaVersion:   SchemaVersion,
			ProtocolVersion: ProtocolVersion,
			OK:              true,
			ExitCode:        ExitOK,
			Command:         command.Name(),
			Result:          result.Result,
		}); err != nil {
			return unexpectedError()
		}
		return nil
	}
	if result.HumanOutput != "" {
		_, _ = io.WriteString(renderer.stdout, result.HumanOutput)
	}
	return nil
}

func (renderer *OutputRenderer) Backend(
	global GlobalOptions,
	command *Command,
	response BackendResponse,
	exitCode int,
) *CLIError {
	if !response.OK {
		failure := backendFailure(response.Error, exitCode)
		renderer.Error(global, command.Name(), failure)
		return failure
	}
	result, human, err := presentResult(command, response.Result)
	if err != nil {
		failure := protocolFailure()
		renderer.Error(global, command.Name(), failure)
		return failure
	}
	if command.Output.Human == HumanDiagnostics && (exitCode == 30 || exitCode == 31) {
		status := "warning"
		if exitCode == 31 {
			status = "error"
		}
		_, _ = fmt.Fprintf(renderer.stderr, "Warning [diagnostic_%s]: %s reported %s checks.\n", status, command.Name(), status)
	}
	if global.JSON {
		if err := json.NewEncoder(renderer.stdout).Encode(outputEnvelope{
			SchemaVersion:   SchemaVersion,
			ProtocolVersion: ProtocolVersion,
			OK:              true,
			ExitCode:        exitCode,
			Command:         command.Name(),
			Result:          result,
		}); err != nil {
			return unexpectedError()
		}
		return nil
	}
	if human != "" {
		_, _ = io.WriteString(renderer.stdout, human)
	}
	return nil
}

func presentResult(command *Command, raw json.RawMessage) (map[string]any, string, error) {
	var source map[string]any
	if err := json.Unmarshal(raw, &source); err != nil || source == nil {
		return nil, "", fmt.Errorf("backend result must be an object")
	}
	projected := make(map[string]any, len(command.Output.ResultKeys))
	for _, key := range command.Output.ResultKeys {
		if value, exists := source[key]; exists {
			projected[key] = value
		}
	}
	switch command.Output.Human {
	case HumanSilent:
		return projected, "", nil
	case HumanToken:
		token, ok := source["token"].(string)
		if !ok || strings.TrimSpace(token) == "" {
			return nil, "", fmt.Errorf("missing one-time token")
		}
		return projected, token + "\n", nil
	case HumanInvitations:
		invitations, ok := source["invitations"].([]any)
		if !ok {
			return nil, "", fmt.Errorf("invalid invitation result")
		}
		var output strings.Builder
		for _, item := range invitations {
			invitation, ok := item.(map[string]any)
			if !ok {
				return nil, "", fmt.Errorf("invalid invitation result")
			}
			token, ok := invitation["token"].(string)
			if !ok || strings.TrimSpace(token) == "" {
				return nil, "", fmt.Errorf("invalid invitation token")
			}
			output.WriteString(token)
			output.WriteByte('\n')
		}
		return projected, output.String(), nil
	case HumanArtifact:
		artifact, ok := source["artifact"].(string)
		if !ok || strings.TrimSpace(artifact) == "" {
			return nil, "", fmt.Errorf("missing artifact name")
		}
		return projected, artifact + "\n", nil
	case HumanDiagnostics:
		output, err := diagnosticOutput(source)
		return projected, output, err
	case HumanPlanStatus:
		output, err := planStatusOutput(source)
		return projected, output, err
	default:
		return nil, "", fmt.Errorf("unsupported output policy")
	}
}

func diagnosticOutput(result map[string]any) (string, error) {
	status, ok := result["status"].(string)
	if !ok || !publicErrorTokenPattern.MatchString(status) {
		return "", fmt.Errorf("invalid diagnostic status")
	}
	checks, ok := result["checks"].([]any)
	if !ok {
		return "", fmt.Errorf("invalid diagnostic checks")
	}
	var output strings.Builder
	fmt.Fprintf(&output, "status: %s\n", status)
	for _, rawCheck := range checks {
		check, ok := rawCheck.(map[string]any)
		if !ok {
			return "", fmt.Errorf("invalid diagnostic check")
		}
		id, idOK := check["id"].(string)
		checkStatus, statusOK := check["status"].(string)
		code, codeOK := check["code"].(string)
		if !idOK || !statusOK || !codeOK || !publicErrorTokenPattern.MatchString(id) || !publicErrorTokenPattern.MatchString(checkStatus) || !publicErrorTokenPattern.MatchString(code) {
			return "", fmt.Errorf("invalid diagnostic check")
		}
		fmt.Fprintf(&output, "%s: %s (%s)\n", id, checkStatus, code)
	}
	return output.String(), nil
}

func planStatusOutput(result map[string]any) (string, error) {
	revision, ok := numericID(result["revision_id"])
	if !ok {
		return "", fmt.Errorf("invalid revision status")
	}
	items, ok := result["technical_items"].([]any)
	if !ok {
		return "", fmt.Errorf("invalid technical status items")
	}
	var output strings.Builder
	fmt.Fprintf(&output, "revision: %d\n", revision)
	for _, rawItem := range items {
		item, ok := rawItem.(map[string]any)
		if !ok {
			return "", fmt.Errorf("invalid technical status item")
		}
		id, idOK := numericID(item["id"])
		status, statusOK := item["status"].(string)
		code, codeOK := item["error_code"].(string)
		if !idOK || !statusOK || !publicErrorTokenPattern.MatchString(status) {
			return "", fmt.Errorf("invalid technical status item")
		}
		if codeOK && code != "" {
			fmt.Fprintf(&output, "item %d: %s (%s)\n", id, status, code)
		} else {
			fmt.Fprintf(&output, "item %d: %s\n", id, status)
		}
	}
	return output.String(), nil
}

func numericID(value any) (int, bool) {
	number, ok := value.(float64)
	if !ok || number <= 0 || number != float64(int(number)) {
		return 0, false
	}
	return int(number), true
}

func backendFailure(backend *BackendError, exitCode int) *CLIError {
	if backend == nil || !knownBackendErrorClasses[backend.Class] || !publicErrorTokenPattern.MatchString(backend.Class) {
		return protocolFailure()
	}
	if exitCode < 20 || exitCode > 49 {
		return unexpectedError()
	}
	message, next := publicBackendMessage(backend.Class)
	failure := &CLIError{
		Class:    backend.Class,
		Message:  message,
		NextStep: next,
		ExitCode: exitCode,
	}
	if publicErrorTokenPattern.MatchString(backend.Phase) {
		failure.Phase = backend.Phase
	}
	failure.Details = safeErrorDetails(backend.Details)
	return failure
}

func protocolFailure() *CLIError {
	return &CLIError{
		Class:    "protocol_incompatible",
		Message:  "The container returned an unsupported administration response.",
		NextStep: "Use a CLI and container built from the same supported release.",
		ExitCode: ExitProtocolIncompatible,
	}
}

func publicBackendMessage(class string) (string, string) {
	switch class {
	case "recipient_key_invalid", "recipient_key_mismatch":
		return "The protected artifact could not be opened with the supplied recipient key.", "Verify the artifact and private key, then retry."
	case "replace_confirmation_required":
		return "Restore requires the separate replacement confirmation.", "Review the target and retry with --replace; --force does not imply it."
	case "irreversible_confirmation_required":
		return "Upgrade requires the separate irreversible-migration confirmation.", "Review the pending migrations and retry with --confirm-irreversible; --force does not imply it."
	case "release_artifact_unverified", "maintenance_required":
		return "The release-bound lifecycle prerequisites are not satisfied.", "Use the matching release CLI and a prepared maintenance container."
	case "source_newer", "source_unsupported", "schema_incompatible", "migration_failed", "rollback_not_supported":
		return "The requested operation is incompatible with the current data or release state.", "Review the supported version and migration path before retrying."
	case "database_not_ready":
		return "The application database is not ready for this administration request.", "Run lzug-admin system doctor and resolve the reported readiness problem."
	case "invalid_request":
		return "The backend rejected the versioned administration request.", "Verify that the CLI and container use the same supported release."
	default:
		return "The administration request could not be completed.", "Review the operation state and retry only after resolving the reported error class."
	}
}

func safeErrorDetails(raw json.RawMessage) map[string]any {
	if len(raw) == 0 {
		return nil
	}
	var source map[string]any
	if json.Unmarshal(raw, &source) != nil {
		return nil
	}
	allowed := map[string]bool{
		"available": true, "current": true, "operation": true,
		"required": true, "state": true, "target": true,
	}
	keys := make([]string, 0, len(source))
	for key := range source {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := map[string]any{}
	for _, key := range keys {
		if !allowed[key] {
			continue
		}
		switch value := source[key].(type) {
		case bool, float64:
			result[key] = value
		case string:
			if len(value) <= 128 && !strings.ContainsAny(value, "\r\n") {
				result[key] = value
			}
		}
	}
	if len(result) == 0 {
		return nil
	}
	return result
}

var knownBackendErrorClasses = map[string]bool{
	"account_conflict": true, "account_exists": true, "account_not_found": true,
	"activation_failed": true, "artifact_content_invalid": true, "artifact_integrity_failed": true,
	"artifact_invalid": true, "artifact_name_invalid": true, "artifact_not_found": true,
	"artifact_write_failed": true, "authentication_key_invalid": true, "authentication_key_missing": true,
	"bootstrap_not_empty": true, "committee_conflict": true, "committee_not_found": true,
	"database_integrity_failed": true, "database_not_ready": true, "document_integrity_failed": true,
	"document_relation_failed": true, "export_invalid": true, "export_secret_detected": true,
	"idempotency_conflict": true, "insufficient_storage": true, "internal_error": true,
	"invalid_request": true, "invitation_not_eligible": true, "irreversible_confirmation_required": true,
	"maintenance_required": true, "manifest_invalid": true, "membership_conflict": true,
	"migration_failed": true, "person_conflict": true, "person_not_found": true,
	"persistence_error": true, "postcheck_failed": true, "recipient_key_invalid": true,
	"recipient_key_mismatch": true, "release_artifact_unverified": true, "replace_confirmation_required": true,
	"restore_failed": true, "restore_requires_backup": true, "rollback_not_supported": true,
	"schema_incompatible": true, "snapshot_failed": true, "source_newer": true,
	"source_unsupported": true, "target_changed": true, "target_invalid": true,
	"token_invalid": true, "upgrade_backup_invalid": true,
}
