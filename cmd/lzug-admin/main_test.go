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
		_, _ = os.Stdout.Write(input)
		_, _ = os.Stderr.WriteString("engine diagnostic")
		os.Exit(23)
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
	if _, err := parseOptions(
		[]string{"--container", "lzug", "test-notification", "--member-id", "7", "--channel", "sms"},
		strings.NewReader(""),
	); err == nil {
		t.Fatal("unsupported delivery channel was accepted")
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
