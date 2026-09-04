package admincli

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestMain(m *testing.M) {
	if os.Getenv("LZUG_ADMINCLI_HELPER") == "1" {
		if delay := os.Getenv("LZUG_ADMINCLI_DELAY"); delay != "" {
			duration, _ := time.ParseDuration(delay)
			time.Sleep(duration)
		}
		if path := os.Getenv("LZUG_ADMINCLI_ARGS_FILE"); path != "" {
			_ = os.WriteFile(path, []byte(strings.Join(os.Args[1:], "\x00")), 0o600)
		}
		args := strings.Join(os.Args[1:], " ")
		if os.Getenv("LZUG_ADMINCLI_INSPECT") == "1" {
			switch {
			case strings.Contains(args, "container inspect"):
				_, _ = os.Stdout.WriteString("sha256:image-id\n")
			case strings.Contains(args, ".RepoDigests"):
				_, _ = os.Stdout.WriteString(os.Getenv("LZUG_ADMINCLI_REPO_DIGESTS") + "\n")
			case strings.Contains(args, ".Config.Labels"):
				_, _ = os.Stdout.WriteString(os.Getenv("LZUG_ADMINCLI_IMAGE_LABELS") + "\n")
			default:
				os.Exit(1)
			}
			os.Exit(0)
		}
		input, _ := io.ReadAll(os.Stdin)
		if path := os.Getenv("LZUG_ADMINCLI_INPUT_FILE"); path != "" {
			_ = os.WriteFile(path, input, 0o600)
		}
		_, _ = os.Stdout.WriteString(os.Getenv("LZUG_ADMINCLI_RESPONSE"))
		_, _ = os.Stderr.WriteString(os.Getenv("LZUG_ADMINCLI_STDERR"))
		code, _ := strconv.Atoi(os.Getenv("LZUG_ADMINCLI_EXIT"))
		os.Exit(code)
	}
	os.Exit(m.Run())
}

func TestContainerTransportHonorsCancellationContext(t *testing.T) {
	t.Setenv("LZUG_ADMINCLI_HELPER", "1")
	t.Setenv("LZUG_ADMINCLI_DELAY", "5s")
	transport := &ContainerTransport{
		Config:   EffectiveConfig{Engine: EffectiveValue{Value: "docker"}, Container: EffectiveValue{Value: "lzug"}},
		Resolver: &fixedEngineResolver{path: os.Args[0]},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, code, err := transport.Execute(ctx, BackendRequest{Version: 1, Command: "status", Arguments: map[string]any{}})
	if code != ExitInterrupted || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("cancelled transport returned code=%d error=%v", code, err)
	}
	if time.Since(started) >= 2*time.Second {
		t.Fatal("transport did not stop the container process promptly")
	}
}

type fixedEngineResolver struct {
	path      string
	preferred []string
}

func (resolver *fixedEngineResolver) Resolve(preferred string) (string, error) {
	resolver.preferred = append(resolver.preferred, preferred)
	return resolver.path, nil
}

func TestContainerTransportUsesOneStdinRequestAndNoShell(t *testing.T) {
	t.Setenv("LZUG_ADMINCLI_HELPER", "1")
	t.Setenv("LZUG_ADMINCLI_RESPONSE", `{"version":1,"ok":false,"error":{"class":"recipient_key_mismatch","message":"safe"}}`+"\n")
	t.Setenv("LZUG_ADMINCLI_STDERR", "untrusted engine diagnostic secret-marker")
	t.Setenv("LZUG_ADMINCLI_EXIT", "27")
	directory := t.TempDir()
	argsFile := filepath.Join(directory, "args")
	inputFile := filepath.Join(directory, "input")
	t.Setenv("LZUG_ADMINCLI_ARGS_FILE", argsFile)
	t.Setenv("LZUG_ADMINCLI_INPUT_FILE", inputFile)
	resolver := &fixedEngineResolver{path: os.Args[0]}
	transport := &ContainerTransport{
		Config: EffectiveConfig{
			Engine:    EffectiveValue{Value: "docker"},
			Container: EffectiveValue{Value: "lzug"},
		},
		Resolver: resolver,
	}
	request := BackendRequest{
		Version: ProtocolVersion,
		Command: "consume-invitation",
		Arguments: map[string]any{
			"token": "secret-marker",
		},
	}
	response, code, err := transport.Execute(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if code != 27 || response.Error == nil || response.Error.Class != "recipient_key_mismatch" {
		t.Fatalf("unexpected transport response: %#v, %d", response, code)
	}
	args, err := os.ReadFile(argsFile)
	if err != nil {
		t.Fatal(err)
	}
	wantArgs := []string{"exec", "--interactive", "lzug", "python", "-m", "backend.admin", "--protocol", "1"}
	if got := strings.Split(string(args), "\x00"); !equalStrings(got, wantArgs) {
		t.Fatalf("unexpected engine argv: %#v", got)
	}
	if strings.Contains(string(args), "secret-marker") || strings.Contains(string(args), "consume-invitation") {
		t.Fatalf("request data reached engine argv: %q", args)
	}
	payload, err := os.ReadFile(inputFile)
	if err != nil {
		t.Fatal(err)
	}
	var decoded BackendRequest
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Command != "consume-invitation" || decoded.Arguments["token"] != "secret-marker" {
		t.Fatalf("unexpected stdin request: %#v", decoded)
	}
}

func TestContainerTransportRejectsMalformedOrMultipleBackendObjects(t *testing.T) {
	for _, payload := range []string{
		`not-json`,
		`{"version":2,"ok":true,"result":{}}`,
		`{"version":1,"ok":true,"result":{}} {"version":1,"ok":true,"result":{}}`,
		`{"version":1,"ok":false,"result":{}}`,
	} {
		t.Setenv("LZUG_ADMINCLI_HELPER", "1")
		t.Setenv("LZUG_ADMINCLI_RESPONSE", payload)
		t.Setenv("LZUG_ADMINCLI_EXIT", "0")
		transport := &ContainerTransport{
			Config:   EffectiveConfig{Engine: EffectiveValue{Value: "docker"}, Container: EffectiveValue{Value: "lzug"}},
			Resolver: &fixedEngineResolver{path: os.Args[0]},
		}
		_, code, err := transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "status", Arguments: map[string]any{}})
		if code != ExitProtocolIncompatible {
			t.Fatalf("malformed payload returned %d: %s", code, payload)
		}
		var runtimeError *RuntimeError
		if !errors.As(err, &runtimeError) || runtimeError.Kind != RuntimeProtocol {
			t.Fatalf("malformed payload returned unexpected error: %v", err)
		}
	}
}

func TestReleaseInspectionRequiresCanonicalMatchingArtifacts(t *testing.T) {
	build := BuildInfo{Version: "0.7.0", Revision: strings.Repeat("a", 40), Tag: "v0.7.0"}
	resolver := &fixedEngineResolver{path: os.Args[0]}
	inspector := &ContainerReleaseInspector{
		Config:   EffectiveConfig{Engine: EffectiveValue{Value: "podman"}, Container: EffectiveValue{Value: "lzug-maintenance"}},
		Resolver: resolver,
	}
	if _, err := inspector.Target(context.Background(), BuildInfo{Version: "development", Revision: "unknown"}); err == nil {
		t.Fatal("development build was accepted for lifecycle work")
	}
	t.Setenv("LZUG_ADMINCLI_HELPER", "1")
	t.Setenv("LZUG_ADMINCLI_INSPECT", "1")
	t.Setenv("LZUG_ADMINCLI_REPO_DIGESTS", `["ghcr.io/lxndrp/lzug@sha256:`+strings.Repeat("c", 64)+`"]`)
	labels, err := json.Marshal(map[string]string{
		"org.opencontainers.image.source":   "https://github.com/lxndrp/lzug",
		"org.opencontainers.image.version":  build.Version,
		"org.opencontainers.image.revision": build.Revision,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("LZUG_ADMINCLI_IMAGE_LABELS", string(labels))
	target, err := inspector.Target(context.Background(), build)
	if err != nil {
		t.Fatal(err)
	}
	if target["image"] != "ghcr.io/lxndrp/lzug@sha256:"+strings.Repeat("c", 64) || target["tag"] != "v0.7.0" {
		t.Fatalf("unexpected release target: %#v", target)
	}

	t.Setenv("LZUG_ADMINCLI_REPO_DIGESTS", `[]`)
	if _, err := inspector.Target(context.Background(), build); err == nil {
		t.Fatal("non-canonical image was accepted")
	}
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
