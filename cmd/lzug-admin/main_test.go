package main

import (
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestMain(m *testing.M) {
	if os.Getenv("LZUG_CLI_HELPER") == "1" {
		if argsPath := os.Getenv("LZUG_CLI_ARGS_FILE"); argsPath != "" {
			_ = os.WriteFile(argsPath, []byte(strings.Join(os.Args[1:], "\x00")), 0o600)
		}
		input, _ := io.ReadAll(os.Stdin)
		exitCode := 23
		if os.Getenv("LZUG_CLI_SAFE_RESPONSE") == "1" {
			_, _ = os.Stdout.WriteString(`{"version":1,"ok":false,"error":{"class":"recipient_key_mismatch","message":"Recipient key does not match"}}` + "\n")
			exitCode = 27
		} else {
			_, _ = os.Stdout.Write(input)
		}
		_, _ = os.Stderr.WriteString("engine diagnostic")
		os.Exit(exitCode)
	}
	os.Exit(m.Run())
}

func TestContainerNamesAreStrictlyValidated(t *testing.T) {
	for _, value := range []string{"lzug", "lzug-prod_1"} {
		if !containerNamePattern.MatchString(value) {
			t.Fatalf("expected valid container name %q", value)
		}
	}
	for _, value := range []string{"", "lzug;rm", "lzug prod", "../lzug", "lzug\x00"} {
		if containerNamePattern.MatchString(value) {
			t.Fatalf("expected invalid container name %q", value)
		}
	}
}

func TestVersionTextUsesBuildMetadata(t *testing.T) {
	previous := applicationVersion
	applicationVersion = "1.2.3"
	t.Cleanup(func() { applicationVersion = previous })
	if got := versionText(); got != "lzug-admin 1.2.3" {
		t.Fatalf("unexpected version text %q", got)
	}
}

func TestCanonicalBuildMetadataUsesLinkedIdentity(t *testing.T) {
	previousVersion := applicationVersion
	previousRevision := applicationRevision
	previousTag := applicationTag
	applicationVersion = "1.2.3-rc.1"
	applicationRevision = strings.Repeat("a", 40)
	applicationTag = "v1.2.3-rc.1"
	t.Cleanup(func() {
		applicationVersion = previousVersion
		applicationRevision = previousRevision
		applicationTag = previousTag
	})

	encoded, err := json.Marshal(cliBuildMetadata())
	if err != nil {
		t.Fatal(err)
	}
	expected := `{"identity":"1.2.3-rc.1","release":true,"revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","tag":"v1.2.3-rc.1"}`
	if string(encoded) != expected {
		t.Fatalf("unexpected build metadata %s", encoded)
	}
}

func TestDiagnosticCommandsUsePortableSecretFreeRequests(t *testing.T) {
	previousVersion := applicationVersion
	previousRevision := applicationRevision
	applicationVersion = "1.2.3"
	applicationRevision = strings.Repeat("a", 40)
	t.Cleanup(func() {
		applicationVersion = previousVersion
		applicationRevision = previousRevision
	})

	var statusPayload string
	for _, engine := range []string{"docker", "podman"} {
		opts, err := parseOptions(
			[]string{"--engine", engine, "--container", "lzug", "status"},
			strings.NewReader(""),
		)
		if err != nil {
			t.Fatal(err)
		}
		payload, err := protocolPayload(opts)
		if err != nil {
			t.Fatal(err)
		}
		if statusPayload == "" {
			statusPayload = string(payload)
		} else if string(payload) != statusPayload {
			t.Fatalf("container engines produced different requests: %q != %q", payload, statusPayload)
		}
	}
	expected := `{"version":1,"command":"status","arguments":{"client":{"identity":"1.2.3","revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}` + "\n"
	if statusPayload != expected {
		t.Fatalf("unexpected status request %q", statusPayload)
	}

	config, err := parseOptions(
		[]string{"--container", "lzug", "config"}, strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := protocolPayload(config)
	if err != nil {
		t.Fatal(err)
	}
	if string(payload) != `{"version":1,"command":"config","arguments":{}}`+"\n" {
		t.Fatalf("unexpected config request %q", payload)
	}
	for _, forbidden := range []string{"token", "password", "sqlite", "/data", "http"} {
		if strings.Contains(strings.ToLower(statusPayload+string(payload)), forbidden) {
			t.Fatalf("diagnostic request contains forbidden value %q", forbidden)
		}
	}
}

func TestDiagnosticCommandsRejectAllUserOptions(t *testing.T) {
	for _, command := range []string{"config", "doctor", "status"} {
		if _, err := parseOptions(
			[]string{"--container", "lzug", command, "--email", "secret@example.invalid"},
			strings.NewReader(""),
		); err == nil {
			t.Fatalf("%s accepted an unrelated option", command)
		}
	}
}

func TestArtifactCommandsUseOnlyTheVersionedBackendContract(t *testing.T) {
	privateKey := "private-key-marker"
	var verifyPayload string
	for _, engine := range []string{"docker", "podman"} {
		opts, err := parseOptions(
			[]string{
				"--engine", engine, "--container", "lzug", "artifact-verify",
				"--artifact", "backup-contract.lzug",
			},
			strings.NewReader(privateKey),
		)
		if err != nil {
			t.Fatal(err)
		}
		payload, err := protocolPayload(opts)
		if err != nil {
			t.Fatal(err)
		}
		if verifyPayload == "" {
			verifyPayload = string(payload)
		} else if string(payload) != verifyPayload {
			t.Fatalf("container engines produced different requests: %q != %q", payload, verifyPayload)
		}
	}
	expectedVerify := `{"version":1,"command":"artifact-verify","arguments":{"artifact":"backup-contract.lzug","recipient_private_key":"private-key-marker"}}` + "\n"
	if verifyPayload != expectedVerify {
		t.Fatalf("unexpected verification request %q", verifyPayload)
	}

	restore, err := parseOptions(
		[]string{
			"--container", "lzug", "backup-restore", "--artifact", "backup-contract.lzug",
			"--replace",
		},
		strings.NewReader(privateKey+"\n"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if restore.arguments["replace"] != true || restore.arguments["recipient_private_key"] != privateKey {
		t.Fatalf("unexpected restore request: %#v", restore)
	}

	export, err := parseOptions(
		[]string{
			"--container", "lzug", "full-export", "--recipient-public-key", "public-key-marker",
		},
		strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	if export.arguments["recipient_public_key"] != "public-key-marker" || len(export.arguments) != 1 {
		t.Fatalf("unexpected full export request: %#v", export)
	}

	backup, err := parseOptions(
		[]string{"--container", "lzug", "backup-create"}, strings.NewReader(""),
	)
	if err != nil || len(backup.arguments) != 0 {
		t.Fatalf("unexpected backup request: %#v, %v", backup, err)
	}
}

func TestArtifactCommandsFailClosedBeforeContainerInvocation(t *testing.T) {
	invalid := []struct {
		args  []string
		input string
	}{
		{[]string{"--container", "lzug", "artifact-verify", "--artifact", "backup.lzug"}, ""},
		{[]string{"--container", "lzug", "artifact-verify", "--artifact", "backup.lzug", "--replace"}, "private"},
		{[]string{"--container", "lzug", "backup-restore"}, "private"},
		{[]string{"--container", "lzug", "backup-restore", "--artifact", "backup.lzug"}, "private\nkey"},
		{[]string{"--container", "lzug", "full-export"}, ""},
		{[]string{"--container", "lzug", "backup-create", "--replace"}, ""},
		{[]string{"--container", "lzug", "status", "--artifact", "backup.lzug"}, ""},
	}
	for _, test := range invalid {
		if _, err := parseOptions(test.args, strings.NewReader(test.input)); err == nil {
			t.Fatalf("invalid artifact command was accepted: %q", test.args)
		}
	}
}

func TestNotificationCommandsUseExplicitSafeArguments(t *testing.T) {
	test, err := parseOptions(
		[]string{"--container", "lzug", "test-notification", "--member-id", "7", "--channel", "web_push"},
		strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	if test.command != "test-notification" || test.arguments["member_id"] != 7 || test.arguments["channel"] != "web_push" {
		t.Fatalf("unexpected test notification request: %#v", test)
	}
	process, err := parseOptions(
		[]string{"--container", "lzug", "process-notifications"}, strings.NewReader(""),
	)
	if err != nil || process.command != "process-notifications" || len(process.arguments) != 0 {
		t.Fatalf("unexpected process notification request: %#v, %v", process, err)
	}
	retry, err := parseOptions(
		[]string{"--container", "lzug", "retry-plan-consequences", "--revision-id", "17"}, strings.NewReader(""),
	)
	if err != nil || retry.command != "retry-plan-consequences" || retry.arguments["revision_id"] != 17 {
		t.Fatalf("unexpected consequence retry request: %#v, %v", retry, err)
	}
	status, err := parseOptions(
		[]string{"--container", "lzug", "plan-consequences-status", "--revision-id", "17"}, strings.NewReader(""),
	)
	if err != nil || status.command != "plan-consequences-status" || status.arguments["revision_id"] != 17 {
		t.Fatalf("unexpected consequence status request: %#v, %v", status, err)
	}
	if _, err := parseOptions(
		[]string{"--container", "lzug", "test-notification", "--member-id", "7", "--channel", "sms"},
		strings.NewReader(""),
	); err == nil {
		t.Fatal("unsupported delivery channel was accepted")
	}
}

func TestCommitteeBootstrapBuildsStrictNestedProtocolArguments(t *testing.T) {
	opts, err := parseOptions(
		[]string{
			"--container", "lzug", "committee-bootstrap",
			"--idempotency-key", "bootstrap-001",
			"--name", "Prüfungsausschuss Nord",
			"--ihk", "IHK Teststadt",
			"--occupation", "Fachinformatiker/in",
			"--chair-first-name", "Erste",
			"--chair-last-name", "Vorsitzende",
			"--chair-email", "chair@example.invalid",
			"--chair-member-status", "ordinary",
			"--chair-representing-side", "employer",
			"--deputy-existing-email", "deputy@example.invalid",
			"--deputy-member-status", "ordinary",
			"--deputy-representing-side", "school",
		},
		strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	if opts.command != "committee-bootstrap" || opts.arguments["idempotency_key"] != "bootstrap-001" {
		t.Fatalf("unexpected bootstrap request: %#v", opts)
	}
	committee := opts.arguments["committee"].(map[string]any)
	if committee["name"] != "Prüfungsausschuss Nord" || committee["ihk"] != "IHK Teststadt" {
		t.Fatalf("unexpected committee arguments: %#v", committee)
	}
	chair := opts.arguments["chair"].(map[string]any)
	deputy := opts.arguments["deputy"].(map[string]any)
	if chair["mode"] != "new" || chair["email"] != "chair@example.invalid" {
		t.Fatalf("unexpected chair arguments: %#v", chair)
	}
	if deputy["mode"] != "existing" || deputy["email"] != "deputy@example.invalid" {
		t.Fatalf("unexpected deputy arguments: %#v", deputy)
	}
	encoded, err := json.Marshal(opts.arguments)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "token") {
		t.Fatalf("bootstrap request must not contain token material: %s", encoded)
	}
}

func TestCommitteeCommandsRejectAmbiguousOrIncompleteSelections(t *testing.T) {
	base := []string{
		"--container", "lzug", "committee-bootstrap",
		"--idempotency-key", "bootstrap-001",
		"--name", "PA Nord", "--ihk", "IHK Test", "--occupation", "Testberuf",
		"--chair-existing-email", "existing@example.invalid",
		"--chair-first-name", "Doppelt",
		"--chair-last-name", "Gewählt",
		"--chair-email", "new@example.invalid",
		"--chair-member-status", "ordinary",
		"--chair-representing-side", "employer",
	}
	if _, err := parseOptions(base, strings.NewReader("")); err == nil {
		t.Fatal("ambiguous person selection was accepted")
	}

	missingMembership := []string{
		"--container", "lzug", "committee-complete",
		"--idempotency-key", "complete-001",
		"--committee-id", "7",
		"--chair-existing-email", "existing@example.invalid",
	}
	if _, err := parseOptions(missingMembership, strings.NewReader("")); err == nil {
		t.Fatal("membership fields were optional")
	}
}

func TestCommitteeLifecycleAndReinviteUseOnlyExplicitArguments(t *testing.T) {
	deactivate, err := parseOptions(
		[]string{
			"--container", "lzug", "committee-deactivate",
			"--idempotency-key", "deactivate-001",
			"--committee-id", "7",
			"--reason", "Technische Sperre",
		},
		strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	if deactivate.arguments["committee_id"] != 7 || deactivate.arguments["reason"] != "Technische Sperre" {
		t.Fatalf("unexpected lifecycle request: %#v", deactivate)
	}

	reinvite, err := parseOptions(
		[]string{
			"--container", "lzug", "committee-reinvite",
			"--idempotency-key", "reinvite-001",
			"--committee-id", "7",
			"--email", "member@example.invalid",
		},
		strings.NewReader(""),
	)
	if err != nil {
		t.Fatal(err)
	}
	if reinvite.arguments["email"] != "member@example.invalid" || len(reinvite.arguments) != 3 {
		t.Fatalf("unexpected reinvite request: %#v", reinvite)
	}
}

func TestTransportPreservesJSONStreamsAndRemoteExitCode(t *testing.T) {
	argsFile := filepath.Join(t.TempDir(), "args")
	t.Setenv("LZUG_CLI_HELPER", "1")
	t.Setenv("LZUG_CLI_ARGS_FILE", argsFile)
	var stdout, stderr strings.Builder
	input := []byte(`{"version":1,"command":"disable","arguments":{"account_id":7}}`)
	code, err := (runner{engine: os.Args[0], container: "lzug"}).execute(
		context.Background(), input, &stdout, &stderr,
	)
	if err != nil {
		t.Fatalf("execute returned an infrastructure error: %v", err)
	}
	if code != 23 {
		t.Fatalf("expected remote exit code 23, got %d", code)
	}
	if stdout.String() != string(input) {
		t.Fatalf("stdout was changed: %q", stdout.String())
	}
	if stderr.String() != "engine diagnostic" {
		t.Fatalf("stderr was changed: %q", stderr.String())
	}
	args, err := os.ReadFile(argsFile)
	if err != nil {
		t.Fatal(err)
	}
	expected := []string{"exec", "--interactive", "lzug", "python", "-m", "backend.admin", "--protocol", "1"}
	if got := strings.Split(string(args), "\x00"); len(got) != len(expected) {
		t.Fatalf("unexpected engine argv: %q", got)
	} else {
		for index := range expected {
			if got[index] != expected[index] {
				t.Fatalf("unexpected engine argv: %q", got)
			}
		}
	}
}

func TestPrivateRecipientKeyUsesStdinAndNeverEngineArgv(t *testing.T) {
	privateKey := "private-key-marker"
	opts, err := parseOptions(
		[]string{
			"--container", "lzug", "artifact-verify", "--artifact", "backup-contract.lzug",
		},
		strings.NewReader(privateKey),
	)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := protocolPayload(opts)
	if err != nil {
		t.Fatal(err)
	}

	argsFile := filepath.Join(t.TempDir(), "args")
	t.Setenv("LZUG_CLI_HELPER", "1")
	t.Setenv("LZUG_CLI_ARGS_FILE", argsFile)
	t.Setenv("LZUG_CLI_SAFE_RESPONSE", "1")
	var stdout, stderr strings.Builder
	code, err := (runner{engine: os.Args[0], container: "lzug"}).execute(
		context.Background(), payload, &stdout, &stderr,
	)
	if err != nil {
		t.Fatalf("execute returned an infrastructure error: %v", err)
	}
	if code != 27 {
		t.Fatalf("expected remote exit code 27, got %d", code)
	}
	engineArgs, err := os.ReadFile(argsFile)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(engineArgs), privateKey) || strings.Contains(stdout.String(), privateKey) || strings.Contains(stderr.String(), privateKey) {
		t.Fatal("private recipient key escaped the stdin protocol channel")
	}
	if !strings.Contains(string(payload), privateKey) {
		t.Fatal("private recipient key was not passed to the backend stdin protocol")
	}
	if _, err := parseOptions(
		[]string{
			"--container", "lzug", "artifact-verify", "--artifact", "backup-contract.lzug",
			"--recipient-private-key", privateKey,
		},
		strings.NewReader(""),
	); err == nil {
		t.Fatal("private recipient key was accepted on argv")
	}
}
