package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"reflect"
	"strings"
	"testing"
)

type fakeConfigResolver struct {
	config  EffectiveConfig
	failure *CLIError
	seen    []GlobalOptions
}

func (resolver *fakeConfigResolver) Resolve(global GlobalOptions) (EffectiveConfig, *CLIError) {
	resolver.seen = append(resolver.seen, global)
	return resolver.config, resolver.failure
}

type fakeInput struct {
	terminal     bool
	confirmation bool
	confirmErr   error
	secrets      map[string]string
	confirmCalls int
	confirmText  []string
	secretCalls  []string
}

func (input *fakeInput) IsTerminal() bool { return input.terminal }

func (input *fakeInput) Confirm(prompt string) (bool, error) {
	input.confirmCalls++
	input.confirmText = append(input.confirmText, prompt)
	return input.confirmation, input.confirmErr
}

func (input *fakeInput) ReadSecret(prompt string) (string, error) {
	input.secretCalls = append(input.secretCalls, prompt)
	value, exists := input.secrets[prompt]
	if !exists {
		return "", errors.New("missing test secret")
	}
	return value, nil
}

type recordingTransport struct {
	requests []BackendRequest
	response BackendResponse
	exitCode int
	err      error
	handle   func(BackendRequest) (BackendResponse, int, error)
}

func (transport *recordingTransport) Execute(_ context.Context, request BackendRequest) (BackendResponse, int, error) {
	transport.requests = append(transport.requests, request)
	if transport.handle != nil {
		return transport.handle(request)
	}
	return transport.response, transport.exitCode, transport.err
}

type fakeInspector struct {
	target map[string]any
	err    error
}

func (inspector *fakeInspector) Target(context.Context, BuildInfo) (map[string]any, error) {
	return inspector.target, inspector.err
}

type fakeRuntimeFactory struct {
	transport *recordingTransport
	inspector *fakeInspector
}

func (runtime *fakeRuntimeFactory) Transport(EffectiveConfig) Transport { return runtime.transport }

func (runtime *fakeRuntimeFactory) ReleaseInspector(EffectiveConfig) ReleaseInspector {
	return runtime.inspector
}

type recordingRenderer struct {
	errors      []*CLIError
	progress    []string
	backendSeen []string
}

func (renderer *recordingRenderer) Error(_ GlobalOptions, _ string, failure *CLIError) {
	renderer.errors = append(renderer.errors, failure)
}

func (*recordingRenderer) Informational(GlobalOptions, any, string) *CLIError {
	return nil
}

func (renderer *recordingRenderer) Progress(_ GlobalOptions, command *Command, phase string, _ int) {
	renderer.progress = append(renderer.progress, command.Name()+":"+phase)
}

func (*recordingRenderer) LocalSuccess(GlobalOptions, *Command, LocalResult) *CLIError {
	return nil
}

func (renderer *recordingRenderer) Backend(_ GlobalOptions, command *Command, _ BackendResponse, _ int) *CLIError {
	renderer.backendSeen = append(renderer.backendSeen, command.Name())
	return nil
}

func testApplication(t *testing.T, response string, exitCode int) (*Application, *recordingTransport, *fakeInput, *bytes.Buffer, *bytes.Buffer) {
	t.Helper()
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	transport := &recordingTransport{response: decodeResponse(t, response), exitCode: exitCode}
	input := &fakeInput{secrets: map[string]string{}}
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}
	application := NewApplication(
		registry,
		BuildInfo{Version: "1.2.3", Revision: strings.Repeat("a", 40), Tag: "v1.2.3"},
		&fakeRuntimeFactory{
			transport: transport,
			inspector: &fakeInspector{target: map[string]any{"identity": "1.2.3", "release": true}},
		},
		&fakeConfigResolver{config: EffectiveConfig{
			Engine:    EffectiveValue{Value: "docker", Source: "default"},
			Container: EffectiveValue{Value: "lzug", Source: "default"},
		}},
		input,
		NewOutputRenderer(stdout, stderr),
	)
	return application, transport, input, stdout, stderr
}

func decodeResponse(t *testing.T, payload string) BackendResponse {
	t.Helper()
	var response BackendResponse
	if err := json.Unmarshal([]byte(payload), &response); err != nil {
		t.Fatal(err)
	}
	return response
}

func TestDirectAndProgrammaticInvocationUseTheSameCommand(t *testing.T) {
	response := `{"version":1,"ok":true,"result":{"account":{"id":7},"kind":"invitation","expires_at":"2026-09-03T00:00:00Z","token":"one-time"}}`
	direct, directTransport, _, _, _ := testApplication(t, response, 0)
	if code := direct.Run(context.Background(), []string{"account", "invite", "--email", "member@example.invalid"}); code != 0 {
		t.Fatalf("direct invocation returned %d", code)
	}
	programmatic, programmaticTransport, _, _, _ := testApplication(t, response, 0)
	if code := programmatic.Execute(
		context.Background(),
		[]string{"account", "invite"},
		[]string{"--email", "member@example.invalid"},
		GlobalOptions{},
	); code != 0 {
		t.Fatalf("programmatic invocation returned %d", code)
	}
	if !reflect.DeepEqual(directTransport.requests, programmaticTransport.requests) {
		t.Fatalf("invocation paths produced different requests: %#v != %#v", directTransport.requests, programmaticTransport.requests)
	}
}

func TestApplicationUsesExplicitRendererImplementation(t *testing.T) {
	application, transport, _, _, _ := testApplication(t, `{"version":1,"ok":true,"result":{"account":{"id":7},"revoked_sessions":1}}`, 0)
	renderer := &recordingRenderer{}
	application.Renderer = renderer
	if code := application.Run(context.Background(), []string{"account", "disable", "--account-id", "7", "--force", "--verbose"}); code != 0 {
		t.Fatalf("command returned %d", code)
	}
	if len(transport.requests) != 1 || !reflect.DeepEqual(renderer.backendSeen, []string{"account disable"}) {
		t.Fatalf("injected dependencies were not used: requests=%d renderer=%#v", len(transport.requests), renderer.backendSeen)
	}
	wantProgress := []string{"account disable:executing", "account disable:completed"}
	if !reflect.DeepEqual(renderer.progress, wantProgress) || len(renderer.errors) != 0 {
		t.Fatalf("unexpected renderer calls: progress=%#v errors=%#v", renderer.progress, renderer.errors)
	}
}

func TestOldFlatSyntaxAndUnknownInputAreRejectedBeforeTransport(t *testing.T) {
	oldCommands := []string{
		"bootstrap", "invite", "disable", "recover", "consume-invitation", "consume-recovery",
		"committee-bootstrap", "committee-complete", "committee-reinvite", "committee-deactivate", "committee-reactivate",
		"config", "doctor", "status", "backup-create", "artifact-verify", "backup-restore", "full-export",
		"upgrade", "rollback", "process-notifications", "test-notification", "plan-consequences-status", "retry-plan-consequences",
	}
	for _, old := range oldCommands {
		application, transport, _, stdout, stderr := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
		if code := application.Run(context.Background(), []string{old}); code != ExitInvalidInvocation {
			t.Fatalf("old command %q returned %d", old, code)
		}
		if len(transport.requests) != 0 || stdout.Len() != 0 || !strings.Contains(stderr.String(), "invalid_invocation") {
			t.Fatalf("old command %q was not rejected locally", old)
		}
	}
	for _, args := range [][]string{
		{"unknown", "run"},
		{"account", "unknown"},
		{"account", "invite", "--unknown"},
		{"account", "invite", "positional"},
	} {
		application, transport, _, _, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
		if code := application.Run(context.Background(), args); code != ExitInvalidInvocation || len(transport.requests) != 0 {
			t.Fatalf("invalid invocation was not rejected: %q", args)
		}
	}
}

func TestHumanSuccessIsSilentExceptForRequiredOneTimeValues(t *testing.T) {
	silent, _, _, stdout, stderr := testApplication(t, `{"version":1,"ok":true,"result":{"account":{"id":7},"revoked_sessions":1}}`, 0)
	if code := silent.Run(context.Background(), []string{"account", "disable", "--account-id", "7", "--force"}); code != 0 {
		t.Fatalf("disable returned %d", code)
	}
	if stdout.Len() != 0 || stderr.Len() != 0 {
		t.Fatalf("successful human command was noisy: stdout=%q stderr=%q", stdout, stderr)
	}

	token, _, _, tokenOut, _ := testApplication(t, `{"version":1,"ok":true,"result":{"account":{"id":7},"kind":"invitation","expires_at":"soon","token":"one-time-token"}}`, 0)
	if code := token.Run(context.Background(), []string{"account", "invite", "--email", "member@example.invalid"}); code != 0 {
		t.Fatalf("invite returned %d", code)
	}
	if tokenOut.String() != "one-time-token\n" {
		t.Fatalf("one-time token was not rendered exactly: %q", tokenOut.String())
	}
}

func TestDiagnosticWarningsStayVisibleOnStderr(t *testing.T) {
	response := `{"version":1,"ok":true,"result":{"command":"doctor","status":"warning","checks":[{"id":"runtime","status":"warning","code":"runtime_unverified"}]}}`
	application, _, _, stdout, stderr := testApplication(t, response, 30)
	if code := application.Run(context.Background(), []string{"system", "doctor"}); code != 30 {
		t.Fatalf("diagnostic returned %d", code)
	}
	if !strings.Contains(stdout.String(), "status: warning") || !strings.Contains(stderr.String(), "Warning [diagnostic_warning]") {
		t.Fatalf("diagnostic warning used the wrong streams: stdout=%q stderr=%q", stdout, stderr)
	}
}

func TestJSONAndVerboseKeepOneObjectOnStdout(t *testing.T) {
	response := `{"version":1,"ok":true,"result":{"account":{"id":7},"revoked_sessions":1,"uncontracted":"discarded"}}`
	application, _, _, stdout, stderr := testApplication(t, response, 0)
	if code := application.Run(context.Background(), []string{"--json", "--verbose", "account", "disable", "--account-id", "7", "--force"}); code != 0 {
		t.Fatalf("JSON invocation returned %d", code)
	}
	var envelope map[string]any
	decoder := json.NewDecoder(bytes.NewReader(stdout.Bytes()))
	if err := decoder.Decode(&envelope); err != nil {
		t.Fatal(err)
	}
	if err := ensureJSONEnd(decoder); err != nil {
		t.Fatalf("stdout contained more than one JSON value: %v", err)
	}
	if envelope["schema_version"] != float64(1) || envelope["protocol_version"] != float64(1) || envelope["exit_code"] != float64(0) || envelope["ok"] != true {
		t.Fatalf("unexpected JSON envelope: %#v", envelope)
	}
	result := envelope["result"].(map[string]any)
	if _, exists := result["uncontracted"]; exists {
		t.Fatalf("uncontracted backend field reached public JSON: %#v", result)
	}
	if !strings.Contains(stderr.String(), "Executing account disable.") || !strings.Contains(stderr.String(), "exit code 0") {
		t.Fatalf("verbose diagnostics were not written to stderr: %q", stderr.String())
	}
}

func TestJSONModeCoversEarlyParserErrorsAndCancellation(t *testing.T) {
	for _, test := range []struct {
		name string
		args []string
		ctx  context.Context
		code int
	}{
		{name: "missing value before json", args: []string{"--engine", "--json", "system", "status"}, ctx: context.Background(), code: ExitInvalidInvocation},
		{name: "invalid json value", args: []string{"--json=invalid", "system", "status"}, ctx: context.Background(), code: ExitInvalidInvocation},
		{name: "cancelled", args: []string{"--json", "system", "status"}, ctx: cancelledContext(), code: ExitInterrupted},
	} {
		t.Run(test.name, func(t *testing.T) {
			application, transport, _, stdout, stderr := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
			if code := application.Run(test.ctx, test.args); code != test.code {
				t.Fatalf("command returned %d", code)
			}
			decoder := json.NewDecoder(bytes.NewReader(stdout.Bytes()))
			var envelope map[string]any
			if err := decoder.Decode(&envelope); err != nil {
				t.Fatal(err)
			}
			if err := ensureJSONEnd(decoder); err != nil {
				t.Fatalf("stdout contained more than one JSON value: %v", err)
			}
			if envelope["exit_code"] != float64(test.code) || envelope["ok"] != false || stderr.Len() != 0 || len(transport.requests) != 0 {
				t.Fatalf("unexpected early JSON failure: envelope=%#v stderr=%q requests=%d", envelope, stderr, len(transport.requests))
			}
		})
	}
}

func cancelledContext() context.Context {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	return ctx
}

func TestBackendErrorsUseStableClassAndCodeWithoutRawText(t *testing.T) {
	secret := "secret-marker"
	response := `{"version":1,"ok":false,"error":{"class":"recipient_key_mismatch","message":"provider leaked ` + secret + `","phase":"precheck"}}`
	for _, jsonMode := range []bool{false, true} {
		application, _, input, stdout, stderr := testApplication(t, response, 27)
		input.secrets["Private recipient key"] = secret
		args := []string{"backup", "verify", "--artifact", "backup.lzug"}
		if jsonMode {
			args = append([]string{"--json"}, args...)
		}
		if code := application.Run(context.Background(), args); code != 27 {
			t.Fatalf("backend error returned %d", code)
		}
		combined := stdout.String() + stderr.String()
		if strings.Contains(combined, "provider leaked") {
			t.Fatalf("raw backend text reached output: %q", combined)
		}
		if !strings.Contains(combined, "recipient_key_mismatch") {
			t.Fatalf("stable backend class is missing: %q", combined)
		}
		if jsonMode {
			var envelope map[string]any
			if err := json.Unmarshal(stdout.Bytes(), &envelope); err != nil {
				t.Fatal(err)
			}
			if envelope["exit_code"] != float64(27) || envelope["ok"] != false {
				t.Fatalf("unexpected JSON error envelope: %#v", envelope)
			}
		} else if stdout.Len() != 0 {
			t.Fatalf("human error wrote stdout: %q", stdout.String())
		}
	}
}

func TestDestructiveConfirmationFailsClosedBeforeTransport(t *testing.T) {
	response := `{"version":1,"ok":true,"result":{"account":{"id":7},"revoked_sessions":1}}`
	nonTTY, transport, _, _, _ := testApplication(t, response, 0)
	if code := nonTTY.Run(context.Background(), []string{"account", "disable", "--account-id", "7"}); code != ExitInvalidInvocation {
		t.Fatalf("non-TTY confirmation returned %d", code)
	}
	if len(transport.requests) != 0 {
		t.Fatal("transport was called without confirmation")
	}

	declined, declinedTransport, input, _, _ := testApplication(t, response, 0)
	input.terminal = true
	input.confirmation = false
	if code := declined.Run(context.Background(), []string{"account", "disable", "--account-id", "7"}); code != ExitInvalidInvocation || len(declinedTransport.requests) != 0 {
		t.Fatal("declined confirmation reached transport")
	}

	accepted, acceptedTransport, acceptedInput, _, _ := testApplication(t, response, 0)
	acceptedInput.terminal = true
	acceptedInput.confirmation = true
	if code := accepted.Run(context.Background(), []string{"account", "disable", "--account-id", "7"}); code != 0 || len(acceptedTransport.requests) != 1 {
		t.Fatal("accepted TTY confirmation did not reach transport")
	}
	if !reflect.DeepEqual(acceptedInput.confirmText, []string{"Disable account 7 and revoke all active sessions?"}) {
		t.Fatalf("confirmation did not identify target and effect: %#v", acceptedInput.confirmText)
	}

	forced, forcedTransport, _, _, _ := testApplication(t, response, 0)
	if code := forced.Run(context.Background(), []string{"account", "disable", "--account-id", "7", "--force"}); code != 0 || len(forcedTransport.requests) != 1 {
		t.Fatal("--force did not skip the ordinary prompt")
	}
}

func TestForceNeverImpliesDangerZoneConfirmation(t *testing.T) {
	application, transport, input, _, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	input.secrets["Private recipient key"] = "private-key"
	transport.handle = func(request BackendRequest) (BackendResponse, int, error) {
		if request.Arguments["replace"] != true {
			return decodeResponse(t, `{"version":1,"ok":false,"error":{"class":"replace_confirmation_required","message":"raw"}}`), 29, nil
		}
		return decodeResponse(t, `{"version":1,"ok":true,"result":{"artifact":"backup.lzug","artifact_type":"backup","artifact_id":"id","snapshot_at":"now","safety_artifact":"pre-restore","phases":[],"readiness":"ready"}}`), 0, nil
	}
	base := []string{"backup", "restore", "--artifact", "backup.lzug", "--force", "--json"}
	if code := application.Run(context.Background(), base); code != 29 {
		t.Fatalf("--force bypassed separate replacement confirmation: %d", code)
	}
	application.Renderer = NewOutputRenderer(&bytes.Buffer{}, &bytes.Buffer{})
	input.secrets["Private recipient key"] = "private-key"
	withDangerFlag := append([]string{}, base...)
	withDangerFlag = append(withDangerFlag, "--replace")
	if code := application.Run(context.Background(), withDangerFlag); code != 0 {
		t.Fatalf("complete danger-zone confirmation returned %d", code)
	}
	if len(transport.requests) != 2 || transport.requests[0].Arguments["replace"] != false || transport.requests[1].Arguments["replace"] != true {
		t.Fatalf("danger-zone request values were not explicit: %#v", transport.requests)
	}
}

func TestCancellationAndProtocolFailuresUseReservedExitCodes(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	application, transport, _, _, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	if code := application.Run(ctx, []string{"system", "status"}); code != ExitInterrupted || len(transport.requests) != 0 {
		t.Fatalf("cancelled invocation returned %d and %d requests", code, len(transport.requests))
	}

	protocol, protocolTransport, _, stdout, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	protocolTransport.err = &RuntimeError{Kind: RuntimeProtocol}
	if code := protocol.Run(context.Background(), []string{"--json", "system", "status"}); code != ExitProtocolIncompatible {
		t.Fatalf("protocol failure returned %d", code)
	}
	if !strings.Contains(stdout.String(), `"class":"protocol_incompatible"`) {
		t.Fatalf("protocol class missing from JSON: %q", stdout.String())
	}
}

func TestConfigInspectReturnsOnlyEffectiveNonSecretValues(t *testing.T) {
	application, transport, _, stdout, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	if code := application.Run(context.Background(), []string{"config", "inspect", "--json"}); code != 0 {
		t.Fatalf("config inspect returned %d", code)
	}
	if len(transport.requests) != 0 {
		t.Fatal("config inspect used transport")
	}
	encoded := stdout.String()
	for _, forbidden := range []string{"secret", "token", "password", "force", "verbose"} {
		if strings.Contains(strings.ToLower(encoded), forbidden) {
			t.Fatalf("config inspect exposed forbidden field %q: %s", forbidden, encoded)
		}
	}
}

func TestInformationalJSONContainsExactlyOneObject(t *testing.T) {
	application, _, _, stdout, _ := testApplication(t, `{"version":1,"ok":true,"result":{}}`, 0)
	if code := application.Run(context.Background(), []string{"--json", "account", "--help"}); code != 0 {
		t.Fatalf("JSON help returned %d", code)
	}
	decoder := json.NewDecoder(bytes.NewReader(stdout.Bytes()))
	var value any
	if err := decoder.Decode(&value); err != nil {
		t.Fatal(err)
	}
	if err := ensureJSONEnd(decoder); err != nil && !errors.Is(err, io.EOF) {
		t.Fatal(err)
	}
}
