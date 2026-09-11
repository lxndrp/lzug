package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestMigrationCommandsRequireSocketBeforeAnyEngineAccess(t *testing.T) {
	app, transport, _, stdout, stderr := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	for _, args := range [][]string{{"upgrade", "status"}, {"upgrade", "rollback"}, {"upgrade", "apply", "--backup-output", "unused", "--identity-file", "unused-key", "--force", "--confirm-irreversible"}} {
		stdout.Reset()
		stderr.Reset()
		if code := app.Run(context.Background(), args); code != ExitInvalidInvocation {
			t.Fatalf("unexpected code %d: %s", code, stderr.String())
		}
		if len(transport.requests) != 0 {
			t.Fatal("upgrade reached legacy adapter")
		}
	}
}

func TestMigrationConfirmationBackupAndApplyOrder(t *testing.T) {
	directory := t.TempDir()
	identity := filepath.Join(directory, "key")
	generated, failure := generateRecipientKeypair(identity, filepath.Join(directory, "recipient"))
	if failure != nil {
		t.Fatal(failure)
	}
	plan := `{"plan_id":"` + strings.Repeat("a", 64) + `","supported":true,"application":{"identity":"0.9.0"},"migration":{"current":"027","target":"028","pending":["028"]},"runtime":{"state":"migration_required"}}`
	recipient, _ := json.Marshal(generated)
	for _, force := range []bool{false, true} {
		app, input, control, _, _ := interactiveApplication(t, nil, successResponse(plan), successResponse(string(recipient)))
		app.Config = &fakeConfigResolver{config: testEndpointConfig("unix:///run/lzug-admin/admin.sock")}
		artifact := app.Runtime.(*dialogRuntimeFactory).artifact.(*queuedArtifactTransport)
		artifact.responses = []BackendResponse{successResponse(`{"artifact_id":"backup"}`), successResponse(`{"artifact_type":"backup"}`), successResponse(`{"job_id":"job","runtime":{"ready":true}}`)}
		artifact.codes = []int{0, 0, 0}
		args := []string{"upgrade", "apply", "--backup-output", filepath.Join(directory, map[bool]string{false: "interactive", true: "forced"}[force]), "--identity-file", identity, "--confirm-irreversible"}
		if force {
			args = append(args, "--force")
		}
		if code := app.Run(context.Background(), args); code != 0 {
			t.Fatalf("apply exit %d", code)
		}
		if len(control.requests) != 2 || control.requests[0].Command != "upgrade-status" || control.requests[1].Command != "backup-recipient-show" {
			t.Fatal("precheck order")
		}
		if len(artifact.requests) != 3 || artifact.requests[0].Command != "backup-package-create" || artifact.requests[1].Command != "artifact-package-verify" || artifact.requests[2].Command != "upgrade-package-apply" {
			t.Fatal("backup/apply order")
		}
		approval := artifact.requests[2]
		if approval.Arguments["confirm_irreversible"] != true || approval.Arguments["plan_id"] != strings.Repeat("a", 64) {
			t.Fatal("approval not bound to inspected plan")
		}
		if !force && (len(input.prompts) != 1 || !strings.Contains(input.prompts[0], "027 -> 028") || !strings.Contains(input.prompts[0], "restore")) {
			t.Fatal("plan and rollback boundary missing before approval")
		}
		payload, _ := json.Marshal(artifact.requests)
		if strings.Contains(string(payload), "AGE-SECRET") || strings.Contains(string(payload), identity) {
			t.Fatal("private identity crossed socket")
		}
	}
}

func TestForceDoesNotApproveIrreversibleMigration(t *testing.T) {
	plan := `{"plan_id":"` + strings.Repeat("a", 64) + `","supported":true}`
	app, _, control, _, _ := interactiveApplication(t, nil, successResponse(plan))
	app.Config = &fakeConfigResolver{config: testEndpointConfig("unix:///run/lzug-admin/admin.sock")}
	code := app.Run(context.Background(), []string{"upgrade", "apply", "--backup-output", "unused", "--identity-file", "unused-key", "--force"})
	if code != ExitInvalidInvocation || len(control.requests) != 1 {
		t.Fatal("force implied irreversible approval")
	}
	if len(app.Runtime.(*dialogRuntimeFactory).artifact.(*queuedArtifactTransport).requests) != 0 {
		t.Fatal("backup or mutation before approval")
	}
}

// TestSocketMigrationLive runs with a real Linux authoritative backend. The
// setup invocation generates identities only in the operator's test directory.
func TestSocketMigrationLive(t *testing.T) {
	directory := os.Getenv("LZUG_MIGRATION_TEST_DIRECTORY")
	if directory == "" {
		t.Skip("run through backend socket migration suite")
	}
	endpoint := os.Getenv("LZUG_MIGRATION_TEST_ENDPOINT")
	identity := filepath.Join(directory, "identity")
	if endpoint == "" {
		if _, failure := generateRecipientKeypair(identity, filepath.Join(directory, "recipient")); failure != nil {
			t.Fatal(failure)
		}
		return
	}
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	app := NewApplication(registry, BuildInfo{Version: "0.9.0", Revision: strings.Repeat("a", 40), Tag: "v0.9.0"}, NewTargetRuntimeFactory(), &fakeConfigResolver{config: testEndpointConfig(endpoint)}, &fakeInput{}, NewOutputRenderer(stdout, stderr))
	args := []string{"--json", "upgrade", "apply", "--backup-output", filepath.Join(directory, "backup.lzug"), "--identity-file", identity, "--confirm-irreversible", "--force"}
	if code := app.Run(context.Background(), args); code != 0 {
		t.Fatalf("real migration exit %d: %s %s", code, stdout.String(), stderr.String())
	}
	var response struct {
		Result struct {
			JobID   string `json:"job_id"`
			Runtime struct {
				Ready bool `json:"ready"`
			} `json:"runtime"`
		} `json:"result"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &response); err != nil || !response.Result.Runtime.Ready || !socketID.MatchString(response.Result.JobID) {
		t.Fatalf("migration result: %s", stdout.String())
	}
	stdout.Reset()
	stderr.Reset()
	if code := app.Run(context.Background(), []string{"--json", "upgrade", "status", "--job-id", response.Result.JobID}); code != 0 || !strings.Contains(stdout.String(), "succeeded") {
		t.Fatal("real migration job lookup failed")
	}
	stdout.Reset()
	stderr.Reset()
	if code := app.Run(context.Background(), []string{"--json", "upgrade", "rollback"}); code != 28 || !strings.Contains(stdout.String(), "rollback_not_supported") {
		t.Fatal("real rollback boundary failed")
	}
	key := string(mustRead(t, identity))
	if strings.Contains(stdout.String(), key) || strings.Contains(stderr.String(), key) {
		t.Fatal("private key leaked")
	}
}
