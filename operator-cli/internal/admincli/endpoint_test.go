package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func testEndpointConfig(endpoint string) EffectiveConfig {
	config := EffectiveConfig{}
	setTargetValue(&config, "endpoint", endpoint, "test")
	setTargetValue(&config, "target-name", "Synthetic target", "test")
	return config
}

func endpointServer(t *testing.T, serve func(net.Conn)) string {
	t.Helper()
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	var handlers sync.WaitGroup
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			connection, err := listener.Accept()
			if err != nil {
				return
			}
			handlers.Add(1)
			go func() {
				defer handlers.Done()
				defer connection.Close()
				_ = connection.SetDeadline(time.Now().Add(5 * time.Second))
				serve(connection)
			}()
		}
	}()
	t.Cleanup(func() { _ = listener.Close(); <-done; handlers.Wait() })
	return "tcp://" + listener.Addr().String()
}

func endpointResult(t *testing.T, connection net.Conn, request BackendRequest) {
	t.Helper()
	code := 0
	result := json.RawMessage(`{"version":1,"ok":true,"result":{"command":"status","status":"ok","checks":[]}}`)
	testWriteEnvelope(t, connection, socketEnvelope{Type: "result", JobID: testSocketJob, CorrelationID: testSocketCorrelation, Command: request.Command, Status: "succeeded", ExitCode: &code, Response: result})
}

func TestEndpointValidationAndPrecedence(t *testing.T) {
	for _, endpoint := range []string{"tcp://example.com:1234", "tcp://0.0.0.0:1234", "tcp://192.0.2.1:1234", "tcp://[::]:1234", "tcp://127.0.0.1:0", "tcp://127.0.0.1:65536", "tcp://127.0.0.1:+12", "tcp://user@127.0.0.1:12", "tcp://127.0.0.1:12/?x", "unix://relative", "invalid://host/socket", "unix:///tmp/%2e/socket", "unix:///tmp/\nsecret"} {
		if _, _, err := parseEndpoint(endpoint); err == nil {
			t.Error("unsafe endpoint accepted", endpoint)
		}
	}
	for _, endpoint := range []string{"tcp://127.0.0.1:1234", "tcp://[::1]:1234"} {
		if _, _, err := parseEndpoint(endpoint); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := parseEndpoint("unix:///tmp/admin.sock"); (err == nil) != (runtime.GOOS != "windows") {
		t.Fatal("Unix platform contract")
	}
	resolver := &SystemConfigResolver{Environment: func() []string { return []string{"LZUG_ADMIN_ENDPOINT=tcp://127.0.0.1:1235"} }, UserConfigDir: func() (string, error) { return t.TempDir(), nil }, ReadFile: func(string) ([]byte, error) {
		return []byte(`{"endpoint":"tcp://127.0.0.1:1234","target-name":"Synthetic"}`), nil
	}}
	global, _, failure := parseGlobalOptions([]string{"--endpoint", "tcp://127.0.0.1:1236", "system", "status"})
	if failure != nil {
		t.Fatal(failure)
	}
	config, failure := resolver.Resolve(global)
	if failure != nil || config.target("endpoint") != "tcp://127.0.0.1:1236" || config.Target["endpoint"].Source != "flag" {
		t.Fatalf("precedence: %#v %#v", config, failure)
	}
	config.Container.Value = "legacy"
	if validateTarget(config) == nil {
		t.Fatal("mixed target accepted")
	}
}

func TestEndpointApplicationOwnsOnlyConnectionsAndFreezesSession(t *testing.T) {
	// Socket access works without external executables.
	t.Setenv("PATH", t.TempDir())
	var requests, closed atomic.Int32
	endpoint := endpointServer(t, func(connection net.Conn) {
		testSocketHello(t, connection)
		request := testSocketRequest(t, connection)
		if request.Command != "status" {
			t.Error("different backend request")
		}
		requests.Add(1)
		endpointResult(t, connection, request)
		var extra [1]byte
		if n, err := connection.Read(extra[:]); n != 0 || err != io.EOF {
			t.Error("client connection left open")
		}
		closed.Add(1)
	})
	application, _, _, _, _ := interactiveApplication(t, []string{"system", "status", "system", "status", "beenden"})
	application.Runtime = NewTargetRuntimeFactory()
	var reads int
	application.Config = &SystemConfigResolver{Environment: func() []string { return nil }, UserConfigDir: func() (string, error) { return t.TempDir(), nil }, ReadFile: func(string) ([]byte, error) {
		reads++
		target := endpoint
		if reads > 1 {
			target = "tcp://192.0.2.1:1234"
		}
		return []byte(fmt.Sprintf(`{"endpoint":%q}`, target)), nil
	}}
	if code := application.Run(context.Background(), []string{"cli"}); code != 0 {
		t.Fatal(code)
	}
	if reads != 1 || requests.Load() != 2 {
		t.Fatal("session target changed")
	}
	application.Config = &fakeConfigResolver{config: testEndpointConfig(endpoint)}
	if code := application.Run(context.Background(), []string{"system", "status"}); code != 0 {
		t.Fatal("external endpoint did not survive session", code)
	}
	if requests.Load() != 3 {
		t.Fatal("request duplicated")
	}
}

func TestEndpointUnixPreservesExternalSocket(t *testing.T) {
	path := socketTestServer(t, func(connection net.Conn) {
		testSocketHello(t, connection)
		endpointResult(t, connection, testSocketRequest(t, connection))
	})
	application, _, _, _, _ := interactiveApplication(t, nil)
	application.Runtime = NewTargetRuntimeFactory()
	application.Config = &fakeConfigResolver{config: testEndpointConfig("unix://" + path)}
	if code := application.Run(context.Background(), []string{"system", "status"}); code != ExitOK {
		t.Fatal("Unix endpoint command failed", code)
	}
	if info, err := os.Stat(path); err != nil || info.Mode()&os.ModeSocket == 0 {
		t.Fatal("CLI removed the externally owned socket")
	}
}

func TestEndpointHandshakeLossAndCancellationNeverRetry(t *testing.T) {
	for _, mode := range []string{"version", "lost", "cancel", "timeout"} {
		t.Run(mode, func(t *testing.T) {
			received := make(chan struct{})
			var requests atomic.Int32
			endpoint := endpointServer(t, func(connection net.Conn) {
				if mode == "version" {
					_, _ = readSocketFrame(connection)
					testWriteEnvelope(t, connection, socketEnvelope{Type: "hello", Protocol: 99, Schema: 1, JobID: testSocketJob, CorrelationID: testSocketCorrelation})
					var extra [1]byte
					if n, _ := connection.Read(extra[:]); n != 0 {
						t.Error("business data before handshake")
					}
					return
				}
				testSocketHello(t, connection)
				_ = testSocketRequest(t, connection)
				requests.Add(1)
				close(received)
				if mode == "lost" {
					return
				}
				var extra [1]byte
				_, _ = connection.Read(extra[:])
			})
			ctx, cancel := context.WithTimeout(context.Background(), 400*time.Millisecond)
			defer cancel()
			if mode == "cancel" {
				go func() { <-received; cancel() }()
			}
			_, _, err := (&SocketTransport{Endpoint: endpoint}).Execute(ctx, BackendRequest{Version: 1, Command: "mutate", Arguments: map[string]any{"secret": "synthetic-secret"}})
			failure := runtimeFailure(err)
			want := map[string]string{"version": "version_incompatible", "lost": "result_unavailable", "cancel": "interrupted", "timeout": "timeout"}[mode]
			if failure.Class != want {
				t.Fatalf("failure: %#v", failure)
			}
			if mode != "version" && (!unknownOutcome(failure) || failure.Details["job_id"] != testSocketJob || requests.Load() != 1) {
				t.Fatalf("unsafe outcome: %#v", failure)
			}
			var stdout, stderr bytes.Buffer
			NewOutputRenderer(&stdout, &stderr).Error(GlobalOptions{JSON: true}, "system status", failure)
			var value any
			decoder := json.NewDecoder(&stdout)
			if decoder.Decode(&value) != nil || decoder.Decode(&value) != io.EOF || strings.Contains(stderr.String(), "synthetic-secret") {
				t.Fatal("unsafe JSON or secret output")
			}
		})
	}
}

func TestEndpointTCPArtifactHalfClose(t *testing.T) {
	for _, direction := range []string{"upload", "download"} {
		t.Run(direction, func(t *testing.T) {
			content := bytes.Repeat([]byte("synthetic-stream"), 20000)
			endpoint := endpointServer(t, func(connection net.Conn) {
				request := testStreamReady(t, connection, direction, maxSocketStream)
				if direction == "upload" {
					var received bytes.Buffer
					ready := socketEnvelope{MaxDataBytes: maxSocketData, MaxStreamBytes: maxSocketStream}
					if terminal, err := receiveSocketArtifact(context.Background(), connection, &received, ready); err != nil || terminal != nil {
						t.Error("invalid upload")
					}
					var extra [1]byte
					if n, err := connection.Read(extra[:]); n != 0 || err != io.EOF {
						t.Error("missing upload half-close")
					}
					if !bytes.Equal(received.Bytes(), content) {
						t.Error("payload changed")
					}
				} else {
					for offset := 0; offset < len(content); offset += maxSocketData {
						if err := writeSocketData(connection, content[offset:min(offset+maxSocketData, len(content))]); err != nil {
							t.Error(err)
							return
						}
					}
					testStreamEnd(t, connection, content)
				}
				testStreamResult(t, connection, request.Command)
			})
			transport := &SocketTransport{Endpoint: endpoint}
			if direction == "upload" {
				response, _, err := transport.Consume(context.Background(), testArtifactRequest("artifact-package-verify"), bytes.NewReader(content))
				if err != nil || !response.OK {
					t.Fatalf("upload: %#v", err)
				}
			} else {
				var result bytes.Buffer
				response, _, err := transport.Produce(context.Background(), testArtifactRequest("backup-package-create"), &result)
				if err != nil || !response.OK || !bytes.Equal(result.Bytes(), content) {
					t.Fatalf("download: %#v", err)
				}
			}
		})
	}
}
