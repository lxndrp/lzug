package admincli

import (
	"context"
	"reflect"
	"strings"
	"testing"
)

func TestEveryBackendCommandBuildsTheExistingVersionedRequest(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	committeePerson := []string{
		"--chair-existing-email", "chair@example.invalid",
		"--chair-member-status", "ordinary",
		"--chair-representing-side", "employer",
	}
	cases := []struct {
		path    string
		args    []string
		secrets Values
		backend string
		assert  func(*testing.T, BackendRequest)
	}{
		{path: "account bootstrap", args: []string{"--email", "operator@example.invalid"}, backend: "bootstrap"},
		{path: "account invite", args: []string{"--email", "member@example.invalid"}, backend: "invite"},
		{path: "account disable", args: []string{"--account-id", "7"}, backend: "disable"},
		{path: "account recover", args: []string{"--email", "member@example.invalid"}, backend: "recover"},
		{path: "account consume-invitation", secrets: Values{"token": "invitation-token"}, backend: "consume-invitation"},
		{path: "account consume-recovery", secrets: Values{"token": "recovery-token"}, backend: "consume-recovery"},
		{
			path: "committee bootstrap",
			args: append([]string{
				"--idempotency-key", "bootstrap-001", "--name", "PA Nord",
				"--ihk", "IHK Teststadt", "--occupation", "Testberuf",
			}, committeePerson...),
			backend: "committee-bootstrap",
			assert: func(t *testing.T, request BackendRequest) {
				committee := request.Arguments["committee"].(map[string]any)
				if committee["name"] != "PA Nord" {
					t.Fatalf("unexpected committee: %#v", committee)
				}
			},
		},
		{path: "committee complete", args: append([]string{"--idempotency-key", "complete-001", "--committee-id", "7"}, committeePerson...), backend: "committee-complete"},
		{path: "committee reinvite", args: []string{"--idempotency-key", "reinvite-001", "--committee-id", "7", "--email", "member@example.invalid"}, backend: "committee-reinvite"},
		{path: "committee deactivate", args: []string{"--idempotency-key", "deactivate-001", "--committee-id", "7", "--reason", "Operator decision"}, backend: "committee-deactivate"},
		{path: "committee reactivate", args: []string{"--idempotency-key", "reactivate-001", "--committee-id", "7", "--reason", "Operator decision"}, backend: "committee-reactivate"},
		{path: "system config", backend: "config"},
		{path: "system status", backend: "status", assert: assertClientMetadata},
		{path: "system doctor", backend: "doctor", assert: assertClientMetadata},
		{path: "backup create", backend: "backup-create"},
		{path: "backup verify", args: []string{"--artifact", "backup.lzug"}, secrets: Values{"recipient-private-key": "private-key"}, backend: "artifact-verify"},
		{path: "backup restore", args: []string{"--artifact", "backup.lzug", "--replace"}, secrets: Values{"recipient-private-key": "private-key"}, backend: "backup-restore"},
		{path: "export create", args: []string{"--recipient-public-key", "public-key"}, backend: "full-export"},
		{path: "export verify", args: []string{"--artifact", "export.lzug"}, secrets: Values{"recipient-private-key": "private-key"}, backend: "artifact-verify"},
		{path: "upgrade apply", args: []string{"--confirm-irreversible"}, secrets: Values{"recipient-private-key": "private-key"}, backend: "upgrade", assert: assertReleaseTarget},
		{path: "upgrade rollback", backend: "rollback", assert: assertReleaseTarget},
		{path: "notification process", backend: "process-notifications"},
		{path: "notification test", args: []string{"--member-id", "7", "--channel", "web_push"}, backend: "test-notification"},
		{path: "plan-consequence status", args: []string{"--revision-id", "17"}, backend: "plan-consequences-status"},
		{path: "plan-consequence retry", args: []string{"--revision-id", "17"}, backend: "retry-plan-consequences"},
	}
	for _, test := range cases {
		t.Run(test.path, func(t *testing.T) {
			command, found := registry.Find(strings.Split(test.path, " "))
			if !found {
				t.Fatal("command is not registered")
			}
			values, failure := parseCommandOptions(command, test.args)
			if failure != nil {
				t.Fatal(failure)
			}
			request, buildErr := command.BuildRequest(
				context.Background(),
				PrepareContext{
					Build: BuildInfo{Version: "1.2.3", Revision: strings.Repeat("a", 40), Tag: "v1.2.3"},
					ReleaseInspector: &fakeInspector{target: map[string]any{
						"identity": "1.2.3", "release": true,
					}},
				},
				values,
				test.secrets,
			)
			if buildErr != nil {
				t.Fatal(buildErr)
			}
			if request.Version != ProtocolVersion || request.Command != test.backend || request.Arguments == nil {
				t.Fatalf("unexpected request: %#v", request)
			}
			if test.assert != nil {
				test.assert(t, request)
			}
		})
	}
}

func assertClientMetadata(t *testing.T, request BackendRequest) {
	t.Helper()
	client := request.Arguments["client"].(map[string]any)
	if client["identity"] != "1.2.3" || client["revision"] != strings.Repeat("a", 40) {
		t.Fatalf("unexpected client metadata: %#v", client)
	}
}

func assertReleaseTarget(t *testing.T, request BackendRequest) {
	t.Helper()
	target := request.Arguments["target"].(map[string]any)
	if target["identity"] != "1.2.3" || target["release"] != true {
		t.Fatalf("unexpected release target: %#v", target)
	}
}

func TestDockerAndPodmanShareIdenticalBackendRequests(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	command, _ := registry.Find([]string{"system", "status"})
	values, failure := parseCommandOptions(command, nil)
	if failure != nil {
		t.Fatal(failure)
	}
	prepare := PrepareContext{Build: BuildInfo{Version: "development", Revision: "unknown"}}
	requests := []BackendRequest{}
	for range []string{"docker", "podman"} {
		request, buildErr := command.BuildRequest(context.Background(), prepare, values, Values{})
		if buildErr != nil {
			t.Fatal(buildErr)
		}
		requests = append(requests, request)
	}
	if !reflect.DeepEqual(requests[0], requests[1]) {
		t.Fatalf("engine selection changed the backend request: %#v", requests)
	}
}

func TestCommandValidationRejectsAmbiguousUnsafeOrSecretArguments(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		path string
		args []string
	}{
		{path: "account recover", args: []string{"--account-id", "7", "--email", "member@example.invalid"}},
		{path: "account recover", args: nil},
		{path: "account disable", args: []string{"--account-id", "0"}},
		{path: "account consume-invitation", args: []string{"--token", "secret"}},
		{path: "backup verify", args: []string{"--artifact", "backup.lzug", "--recipient-private-key", "secret"}},
		{path: "backup restore", args: []string{"--artifact", "unsafe\nname.lzug"}},
		{path: "notification test", args: []string{"--member-id", "7", "--channel", "sms"}},
		{path: "committee bootstrap", args: []string{
			"--idempotency-key", "bootstrap-001", "--name", "PA", "--ihk", "IHK", "--occupation", "Job",
			"--chair-existing-email", "old@example.invalid", "--chair-first-name", "New",
			"--chair-last-name", "Person", "--chair-email", "new@example.invalid",
			"--chair-member-status", "ordinary", "--chair-representing-side", "employer",
		}},
	}
	for _, test := range tests {
		command, _ := registry.Find(strings.Split(test.path, " "))
		if _, failure := parseCommandOptions(command, test.args); failure == nil {
			t.Fatalf("unsafe arguments were accepted for %s: %q", test.path, test.args)
		}
	}
}

func TestRequestsNeverPlaceSecretsInCommandMetadata(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	var publicMetadata strings.Builder
	publicMetadata.WriteString(GenerateReference(registry))
	for _, command := range registry.Commands() {
		help, _ := Help(registry, command.Name())
		publicMetadata.WriteString(help)
	}
	for _, shell := range []string{"bash", "zsh", "fish", "powershell"} {
		completion, completionErr := GenerateCompletion(registry, shell)
		if completionErr != nil {
			t.Fatal(completionErr)
		}
		publicMetadata.WriteString(completion)
	}
	for _, secret := range []string{"invitation-token", "private-key", "recovery-token"} {
		if strings.Contains(publicMetadata.String(), secret) {
			t.Fatalf("secret value reached registry metadata: %s", secret)
		}
	}
}
