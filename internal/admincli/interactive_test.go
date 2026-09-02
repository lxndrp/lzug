package admincli

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"reflect"
	"strings"
	"testing"
)

type dialogInput struct {
	lines        []string
	lineIndex    int
	terminal     bool
	confirmation bool
	secrets      []string
	secretIndex  int
	prompts      []string
	interruptAt  int
}

func (input *dialogInput) IsTerminal() bool { return input.terminal }

func (input *dialogInput) ReadLine(_ context.Context, prompt string) (string, error) {
	input.prompts = append(input.prompts, prompt)
	if input.interruptAt > 0 && input.lineIndex+1 == input.interruptAt {
		input.lineIndex++
		return "", errInputInterrupted
	}
	if input.lineIndex >= len(input.lines) {
		return "", io.EOF
	}
	value := input.lines[input.lineIndex]
	input.lineIndex++
	return value, nil
}

func (input *dialogInput) Confirm(prompt string) (bool, error) {
	input.prompts = append(input.prompts, prompt)
	return input.confirmation, nil
}

func (input *dialogInput) ReadSecret(prompt string) (string, error) {
	input.prompts = append(input.prompts, prompt)
	if input.secretIndex >= len(input.secrets) {
		return "", errors.New("missing secret")
	}
	value := input.secrets[input.secretIndex]
	input.secretIndex++
	return value, nil
}

type queuedTransport struct {
	responses []BackendResponse
	codes     []int
	requests  []BackendRequest
}

type dialogRuntimeFactory struct {
	transport Transport
	inspector ReleaseInspector
}

type sessionConfigResolver struct{}

func (*sessionConfigResolver) Resolve(global GlobalOptions) (EffectiveConfig, *CLIError) {
	engine := EffectiveValue{Value: "docker", Source: "default"}
	container := EffectiveValue{Value: "lzug", Source: "file"}
	if global.EngineSet {
		engine = EffectiveValue{Value: global.Engine, Source: "flag"}
	}
	if global.ContainerSet {
		container = EffectiveValue{Value: global.Container, Source: "flag"}
	}
	return EffectiveConfig{Engine: engine, Container: container}, nil
}

func (factory *dialogRuntimeFactory) Transport(EffectiveConfig) Transport {
	return factory.transport
}

func (factory *dialogRuntimeFactory) ReleaseInspector(EffectiveConfig) ReleaseInspector {
	return factory.inspector
}

func (transport *queuedTransport) Execute(_ context.Context, request BackendRequest) (BackendResponse, int, error) {
	transport.requests = append(transport.requests, request)
	index := len(transport.requests) - 1
	if index >= len(transport.responses) {
		return BackendResponse{}, ExitUnexpected, fmt.Errorf("unexpected request")
	}
	return transport.responses[index], transport.codes[index], nil
}

func interactiveApplication(t *testing.T, lines []string, responses ...BackendResponse) (*Application, *dialogInput, *queuedTransport, *bytes.Buffer, *bytes.Buffer) {
	t.Helper()
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	input := &dialogInput{lines: lines, terminal: true, confirmation: true}
	transport := &queuedTransport{responses: responses, codes: make([]int, len(responses))}
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}
	renderer := NewOutputRenderer(stdout, stderr)
	renderer.outputTerminal = true
	application := NewApplication(
		registry,
		BuildInfo{Version: "1.2.3", Revision: strings.Repeat("a", 40), Tag: "v1.2.3"},
		&dialogRuntimeFactory{transport: transport, inspector: &fakeInspector{target: map[string]any{"identity": "1.2.3", "release": true}}},
		&fakeConfigResolver{config: EffectiveConfig{
			Engine:    EffectiveValue{Value: "docker", Source: "default"},
			Container: EffectiveValue{Value: "lzug", Source: "file"},
		}},
		input,
		renderer,
	)
	return application, input, transport, stdout, stderr
}

func successResponse(result string) BackendResponse {
	return decodeResponseForDialog(result)
}

func decodeResponseForDialog(result string) BackendResponse {
	return BackendResponse{Version: ProtocolVersion, OK: true, Result: []byte(result)}
}

func TestInteractiveModeRequiresBothTerminalsAndRejectsAutomationFlags(t *testing.T) {
	application, _, transport, _, stderr := interactiveApplication(t, []string{"beenden"})
	application.Input.(*dialogInput).terminal = false
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitInvalidInvocation {
		t.Fatalf("missing input TTY returned %d", code)
	}
	if len(transport.requests) != 0 || !strings.Contains(stderr.String(), "interactive input and output terminals") {
		t.Fatal("missing input TTY was not rejected before transport")
	}

	application, _, transport, _, _ = interactiveApplication(t, []string{"beenden"})
	application.Renderer.(*OutputRenderer).outputTerminal = false
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitInvalidInvocation || len(transport.requests) != 0 {
		t.Fatal("missing output TTY was not rejected before transport")
	}

	for _, args := range [][]string{{"cli", "--json"}, {"--force", "cli"}, {"cli", "unexpected"}} {
		application, _, transport, _, _ = interactiveApplication(t, nil)
		if code := application.Run(context.Background(), args); code != ExitInvalidInvocation || len(transport.requests) != 0 {
			t.Fatalf("invalid interactive invocation %q was not rejected", args)
		}
	}
}

func TestInteractiveEntrypointKeepsRegistryHelpAvailable(t *testing.T) {
	application, _, transport, stdout, _ := interactiveApplication(t, nil)
	if code := application.Run(context.Background(), []string{"cli", "--help"}); code != ExitOK {
		t.Fatalf("cli help returned %d", code)
	}
	if !strings.Contains(stdout.String(), "lzug-admin cli") || len(transport.requests) != 0 {
		t.Fatalf("cli help did not use the registry without transport: %q", stdout.String())
	}
	if InteractiveRequested([]string{"cli", "--help"}) {
		t.Fatal("help-only invocation was classified as an interactive session")
	}
}

func TestEveryRegistryCommandIsSearchableFromItsDeclaredMetadata(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	for _, command := range registry.Commands() {
		matches := registry.Search(command.Name())
		if !containsCommand(matches, command.Name()) {
			t.Fatalf("command %q is not discoverable by name", command.Name())
		}
		matches = registry.Search(command.Summary)
		if !containsCommand(matches, command.Name()) {
			t.Fatalf("command %q is not discoverable by short help", command.Name())
		}
	}
	if matches := registry.Search("ausschuss"); !containsCommand(matches, "committee bootstrap") {
		t.Fatal("declared search terms were not indexed")
	}
}

func TestInteractiveAndDirectInvocationProduceTheSameBackendRequest(t *testing.T) {
	status := successResponse(`{"command":"status","status":"ok","checks":[]}`)
	invite := successResponse(`{"account":{"id":7},"kind":"invitation","expires_at":"soon","token":"one-time"}`)
	interactive, _, interactiveTransport, stdout, _ := interactiveApplication(t, []string{
		"account", "invite", "member@example.invalid", "beenden",
	}, status, invite)
	if code := interactive.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("interactive invocation returned %d", code)
	}
	if len(interactiveTransport.requests) != 2 || interactiveTransport.requests[0].Command != "status" {
		t.Fatalf("target was not checked exactly once before the command: %#v", interactiveTransport.requests)
	}

	direct, directTransport, _, _, _ := testApplication(t, `{"version":1,"ok":true,"result":{"account":{"id":7},"kind":"invitation","expires_at":"soon","token":"one-time"}}`, 0)
	if code := direct.Run(context.Background(), []string{"account", "invite", "--email", "member@example.invalid"}); code != ExitOK {
		t.Fatalf("direct invocation returned %d", code)
	}
	if !reflect.DeepEqual(interactiveTransport.requests[1], directTransport.requests[0]) {
		t.Fatalf("interactive request differs from direct request: %#v != %#v", interactiveTransport.requests[1], directTransport.requests[0])
	}
	if !strings.Contains(stdout.String(), "Ergebnis: account invite erfolgreich (Exit Code 0).") || !strings.Contains(stdout.String(), "Sitzung beendet.") {
		t.Fatalf("session outcome is unclear: %q", stdout.String())
	}
}

func TestLocalCommandWorksWithoutContainerAndUnavailableCommandsStayVisible(t *testing.T) {
	application, _, transport, stdout, _ := interactiveApplication(t, []string{"account", "zurueck", "config", "inspect", "beenden"})
	application.Config = &fakeConfigResolver{config: EffectiveConfig{
		Engine:    EffectiveValue{Value: "auto", Source: "default"},
		Container: EffectiveValue{Value: "", Source: "default"},
	}}
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("session returned %d", code)
	}
	output := stdout.String()
	if !strings.Contains(output, "account") || !strings.Contains(output, "kein Container im Sitzungsziel") || !strings.Contains(output, "Ergebnis: config inspect erfolgreich") {
		t.Fatalf("availability or local execution is missing: %q", output)
	}
	if len(transport.requests) != 0 {
		t.Fatal("local command used backend transport")
	}
}

func TestMutatingCommandShowsSummaryAndUsesConcreteConfirmation(t *testing.T) {
	status := successResponse(`{"command":"status","status":"ok","checks":[]}`)
	disabled := successResponse(`{"account":{"id":7},"revoked_sessions":1}`)
	application, input, transport, stdout, _ := interactiveApplication(t, []string{
		"account", "disable", "7", "beenden",
	}, status, disabled)
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("session returned %d", code)
	}
	if len(transport.requests) != 2 {
		t.Fatalf("expected handshake and mutation, got %d requests", len(transport.requests))
	}
	if !strings.Contains(stdout.String(), "Zusammenfassung vor der Ausführung") || !strings.Contains(stdout.String(), "account-id: 7") {
		t.Fatalf("mutation summary is incomplete: %q", stdout.String())
	}
	found := false
	for _, prompt := range input.prompts {
		if strings.Contains(prompt, "Disable account 7") {
			found = true
		}
	}
	if !found {
		t.Fatalf("concrete confirmation was not reused: %#v", input.prompts)
	}
}

func TestInteractiveSecretsAreNeverRenderedOrReused(t *testing.T) {
	secret := "private-secret-marker"
	status := successResponse(`{"command":"status","status":"ok","checks":[]}`)
	verified := successResponse(`{"artifact":"backup.lzug","artifact_type":"backup","verification":{"ok":true}}`)
	application, input, transport, stdout, stderr := interactiveApplication(t, []string{
		"backup", "verify", "backup.lzug", "beenden",
	}, status, verified)
	input.secrets = []string{secret}
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("session returned %d", code)
	}
	combined := stdout.String() + stderr.String() + strings.Join(input.prompts, "\n")
	if strings.Contains(combined, secret) {
		t.Fatal("secret reached dialog output or prompts")
	}
	if input.secretIndex != 1 || len(transport.requests) != 2 {
		t.Fatalf("secret input or transport count is wrong: secrets=%d requests=%d", input.secretIndex, len(transport.requests))
	}
	if got := transport.requests[1].Arguments["recipient_private_key"]; got != secret {
		t.Fatal("secret did not reach the existing request builder")
	}
}

func TestSafeRetryRecapturesSecretsAndNeverReusesConfirmation(t *testing.T) {
	secret := "private-secret-marker"
	status := successResponse(`{"command":"status","status":"ok","checks":[]}`)
	failure := BackendResponse{Version: ProtocolVersion, OK: false, Error: &BackendError{Class: "artifact_integrity_failed"}}
	verified := successResponse(`{"artifact":"backup.lzug","artifact_type":"backup","verification":{"ok":true}}`)
	application, input, transport, stdout, stderr := interactiveApplication(t, []string{
		"backup", "verify", "backup.lzug", "ja", "beenden",
	}, status, failure, verified)
	input.secrets = []string{secret, secret}
	transport.codes[1] = 23
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("session returned %d", code)
	}
	if input.secretIndex != 2 || len(transport.requests) != 3 {
		t.Fatalf("safe retry did not recapture the secret: secrets=%d requests=%d", input.secretIndex, len(transport.requests))
	}
	if !strings.Contains(stdout.String(), "Geheimnisse werden für die Wiederholung erneut erfasst") {
		t.Fatalf("retry contract was not explained: %q", stdout.String())
	}
	if strings.Contains(stdout.String()+stderr.String(), secret) {
		t.Fatal("secret leaked during retry")
	}
}

func TestTargetChangeRequiresANewHandshake(t *testing.T) {
	status := successResponse(`{"command":"status","status":"ok","checks":[]}`)
	invite := successResponse(`{"account":{"id":7},"kind":"invitation","expires_at":"soon","token":"one-time"}`)
	application, _, transport, stdout, _ := interactiveApplication(t, []string{
		"account", "invite", "first@example.invalid",
		"ziel", "", "lzug-next",
		"account", "invite", "second@example.invalid",
		"beenden",
	}, status, invite, status, invite)
	application.Config = &sessionConfigResolver{}
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("session returned %d", code)
	}
	if len(transport.requests) != 4 || transport.requests[0].Command != "status" || transport.requests[2].Command != "status" {
		t.Fatalf("target change did not invalidate the handshake: %#v", transport.requests)
	}
	if !strings.Contains(stdout.String(), "container=lzug-next (session)") {
		t.Fatalf("session target and source were not displayed: %q", stdout.String())
	}
}

func TestSessionExitCodesAreIndependentFromHandledCommandFailures(t *testing.T) {
	statusFailure := BackendResponse{Version: ProtocolVersion, OK: false, Error: &BackendError{Class: "database_not_ready"}}
	application, _, transport, stdout, _ := interactiveApplication(t, []string{
		"system", "status", "beenden",
	}, statusFailure)
	transport.codes[0] = 21
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("regular session exit inherited a command failure: %d", code)
	}
	if !strings.Contains(stdout.String(), "database_not_ready, Exit Code 21") {
		t.Fatalf("command error class and code were not shown: %q", stdout.String())
	}

	cancelled, _, _, _, _ := interactiveApplication(t, nil)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if code := cancelled.Run(ctx, []string{"cli"}); code != ExitInterrupted {
		t.Fatalf("Ctrl+C-equivalent context returned %d", code)
	}
}

func TestCtrlCBeforeExecutionReturnsToThePreviousLevel(t *testing.T) {
	application, input, transport, stdout, _ := interactiveApplication(t, []string{"account", "", "beenden"})
	input.interruptAt = 2
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitOK {
		t.Fatalf("nested Ctrl+C ended the session with %d", code)
	}
	if len(transport.requests) != 0 {
		t.Fatal("nested Ctrl+C sent a transport request")
	}
	if strings.Count(stdout.String(), "Objekt wählen:") < 2 {
		t.Fatalf("nested Ctrl+C did not return to the main menu: %q", stdout.String())
	}

	application, input, _, stdout, _ = interactiveApplication(t, []string{""})
	input.interruptAt = 1
	if code := application.Run(context.Background(), []string{"cli"}); code != ExitInterrupted {
		t.Fatalf("main-menu Ctrl+C returned %d", code)
	}
	if !strings.Contains(stdout.String(), "Sitzung durch Ctrl+C beendet") {
		t.Fatalf("main-menu Ctrl+C was not explained: %q", stdout.String())
	}
}

func TestDialogOutputWrapsWithoutANSIOrInformationLoss(t *testing.T) {
	input := "  This is a deliberately long line whose complete content must remain available in a narrow terminal.\n"
	wrapped := wrapDialog(input, 28)
	if strings.Contains(wrapped, "\x1b[") {
		t.Fatal("line-oriented dialog unexpectedly depends on ANSI")
	}
	if strings.Join(strings.Fields(wrapped), " ") != strings.Join(strings.Fields(input), " ") {
		t.Fatalf("wrapping lost content: %q", wrapped)
	}
	for _, line := range strings.Split(strings.TrimSuffix(wrapped, "\n"), "\n") {
		if len([]rune(line)) > 28 {
			t.Fatalf("line exceeds terminal width: %q", line)
		}
	}
}

func containsCommand(commands []*Command, name string) bool {
	for _, command := range commands {
		if command.Name() == name {
			return true
		}
	}
	return false
}
