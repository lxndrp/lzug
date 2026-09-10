package admincli

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"filippo.io/age"
)

func testArtifactRequest(command string) BackendRequest {
	arguments := map[string]any{"recipient_key_fingerprint": "sha256:" + strings.Repeat("a", 64)}
	if command == "artifact-package-verify" {
		arguments = map[string]any{"artifact_type": "backup"}
	}
	return BackendRequest{Command: command, Arguments: arguments}
}

func testStreamReady(t *testing.T, connection net.Conn, direction string, limit int64) BackendRequest {
	t.Helper()
	testSocketHello(t, connection)
	request := testSocketRequest(t, connection)
	testWriteEnvelope(t, connection, socketEnvelope{Type: "stream-ready", JobID: testSocketJob, CorrelationID: testSocketCorrelation, Direction: direction, MaxDataBytes: maxSocketData, MaxStreamBytes: limit})
	return request
}

func testStreamEnd(t *testing.T, connection net.Conn, content []byte) {
	t.Helper()
	digest := sha256.Sum256(content)
	count := int64(len(content))
	testWriteEnvelope(t, connection, socketEnvelope{Type: "stream-end", Bytes: &count, SHA256: hex.EncodeToString(digest[:])})
}

func testStreamResult(t *testing.T, connection net.Conn, command string) {
	t.Helper()
	code := 0
	testWriteEnvelope(t, connection, socketEnvelope{Type: "result", JobID: testSocketJob, CorrelationID: testSocketCorrelation, Command: command, Status: "succeeded", ExitCode: &code, Response: json.RawMessage(`{"version":1,"ok":true,"result":{"artifact_id":"test"}}`)})
}

func TestSocketArtifactUploadRequiresAuthenticatedEOFAndHalfClose(t *testing.T) {
	content := bytes.Repeat([]byte("clear-package"), 20000)
	path := socketTestServer(t, func(connection net.Conn) {
		request := testStreamReady(t, connection, "upload", maxSocketStream)
		var received bytes.Buffer
		for {
			data, control, err := readSocketPacket(connection)
			if err != nil {
				t.Error(err)
				return
			}
			if data != nil {
				received.Write(data)
				continue
			}
			digest := sha256.Sum256(content)
			if control.Type != "stream-end" || control.Bytes == nil || *control.Bytes != int64(len(content)) || control.SHA256 != hex.EncodeToString(digest[:]) {
				t.Error("invalid terminator")
			}
			break
		}
		if !bytes.Equal(content, received.Bytes()) {
			t.Error("payload changed")
		}
		var extra [1]byte
		if n, err := connection.Read(extra[:]); n != 0 || err != io.EOF {
			t.Error("missing half-close")
		}
		testStreamResult(t, connection, request.Command)
	})
	response, code, err := (&SocketTransport{Path: path}).Consume(context.Background(), testArtifactRequest("artifact-package-verify"), bytes.NewReader(content))
	if err != nil || code != 0 || !response.OK {
		t.Fatal("upload failed", err)
	}
}

func TestSocketArtifactDownloadNeedsEndAndResultBeforeAtomicPublication(t *testing.T) {
	for _, mode := range []string{"success", "missing-end", "missing-result", "wrong-digest", "result-first", "result-before-ready", "extra-data"} {
		t.Run(mode, func(t *testing.T) {
			content := []byte("clear-package")
			path := socketTestServer(t, func(connection net.Conn) {
				if mode == "result-before-ready" {
					testSocketHello(t, connection)
					request := testSocketRequest(t, connection)
					testStreamResult(t, connection, request.Command)
					return
				}
				request := testStreamReady(t, connection, "download", maxSocketStream)
				if mode == "result-first" {
					testStreamResult(t, connection, request.Command)
					return
				}
				_ = writeSocketData(connection, content)
				if mode == "missing-end" {
					return
				}
				endContent := content
				if mode == "wrong-digest" {
					endContent = []byte("wrong-content")
				}
				testStreamEnd(t, connection, endContent)
				if mode == "missing-result" || mode == "wrong-digest" {
					return
				}
				testStreamResult(t, connection, request.Command)
				if mode == "extra-data" {
					_, _ = connection.Write([]byte("extra"))
				}
			})
			identity, _ := age.GenerateX25519Identity()
			_, fingerprint, _ := parseRecipient(identity.Recipient().String())
			directory := t.TempDir()
			target := filepath.Join(directory, "backup.lzug")
			_, _, failure := writeProtectedArtifact(context.Background(), target, identity.Recipient(), fingerprint, func(writer io.Writer) (BackendResponse, int, error) {
				return (&SocketTransport{Path: path}).Produce(context.Background(), testArtifactRequest("backup-package-create"), writer)
			})
			if mode == "success" {
				if failure != nil {
					t.Fatal(failure)
				}
				_, _, failure = consumeProtectedArtifact(target, identity, fingerprint, func(reader io.Reader) (BackendResponse, int, error) {
					plain, err := io.ReadAll(reader)
					if err != nil || !bytes.Equal(content, plain) {
						t.Error("local age roundtrip failed")
					}
					return BackendResponse{Version: 1, OK: true}, 0, nil
				})
				if failure != nil {
					t.Fatal(failure)
				}
			} else {
				if failure == nil {
					t.Fatal("partial artifact published")
				}
				entries, _ := os.ReadDir(directory)
				if len(entries) != 0 {
					t.Fatal("partial output remains")
				}
				if failure.Details["job_id"] != testSocketJob {
					t.Fatal("lost job ID")
				}
			}
		})
	}
}

func TestSocketStreamRejectsOversizeAndAmbiguousControlBeforeReadingPayload(t *testing.T) {
	for _, header := range [][]byte{{0x80, 1, 0, 1}, {0x80, 0, 0, 0}, {0, 0x10, 0, 1}} {
		if _, _, err := readSocketPacket(bytes.NewReader(header)); err == nil {
			t.Fatal("invalid size accepted")
		}
	}
	for _, value := range []string{`{"type":"stream-end","type":"result"}`, `{"type":"stream-end","bytes":1,"bytes":2}`, `{"type":"result","response":{"ok":true,"ok":false}}`} {
		if _, err := decodeSocketEnvelope([]byte(value)); err == nil {
			t.Fatal("duplicate field accepted")
		}
	}
}

type failedArtifactSource struct{ sent bool }

func (source *failedArtifactSource) Read(target []byte) (int, error) {
	if !source.sent {
		source.sent = true
		return copy(target, []byte("partial")), nil
	}
	return 0, errors.New("PRIVATE-INTEGRITY-ERROR")
}

func TestSocketArtifactSourceFailureAndLimitNeverSendEnd(t *testing.T) {
	for _, source := range []io.Reader{&failedArtifactSource{}, strings.NewReader(strings.Repeat("x", 100))} {
		path := socketTestServer(t, func(connection net.Conn) {
			testStreamReady(t, connection, "upload", 32)
			for {
				data, control, err := readSocketPacket(connection)
				if err != nil {
					return
				}
				if data == nil {
					t.Errorf("unexpected terminal frame: %s", control.Type)
					return
				}
			}
		})
		_, _, err := (&SocketTransport{Path: path}).Consume(context.Background(), testArtifactRequest("artifact-package-verify"), source)
		var failure *SocketTransportError
		if !errors.As(err, &failure) || failure.JobID != testSocketJob || strings.Contains(err.Error(), "PRIVATE") {
			t.Fatal("unsafe source failure")
		}
	}
}

func TestSocketArtifactRejectsIdentityBeforeConnecting(t *testing.T) {
	request := testArtifactRequest("backup-package-create")
	request.Arguments["identity"] = "AGE-SECRET-KEY-NEVER-TRANSMIT"
	_, _, err := (&SocketTransport{Path: "/missing"}).Produce(context.Background(), request, io.Discard)
	var failure *SocketTransportError
	if !errors.As(err, &failure) || failure.Phase != "validation" || failure.OutcomeUnknown {
		t.Fatal("private argument was not rejected locally")
	}
}

func TestSocketArtifactCancellationAndBackpressure(t *testing.T) {
	path := socketTestServer(t, func(connection net.Conn) {
		testStreamReady(t, connection, "upload", maxSocketStream)
		time.Sleep(150 * time.Millisecond)
	})
	ctx, cancel := context.WithCancel(context.Background())
	time.AfterFunc(50*time.Millisecond, cancel)
	started := time.Now()
	_, _, err := (&SocketTransport{Path: path, Timeout: time.Second}).Consume(ctx, testArtifactRequest("artifact-package-verify"), io.LimitReader(zeroArtifactReader{}, maxSocketStream))
	if err == nil || time.Since(started) > time.Second {
		t.Fatal("blocked stream did not cancel")
	}
}

type zeroArtifactReader struct{}

func (zeroArtifactReader) Read(target []byte) (int, error) { clear(target); return len(target), nil }

// Invoked by Python against the authoritative Linux process. Private identities
// are generated only here and are never part of a BackendRequest or wire frame.
func TestSocketArtifactsLive(t *testing.T) {
	path := os.Getenv("LZUG_SOCKET_ARTIFACT_TEST_PATH")
	if path == "" {
		t.Skip("run through backend.tests.test_admin_socket_artifacts")
	}
	factory := &SocketRuntimeFactory{Path: path, Timeout: 30 * time.Second}
	transport := factory.ArtifactTransport(EffectiveConfig{})
	identity, _ := age.GenerateX25519Identity()
	_, fingerprint, _ := parseRecipient(identity.Recipient().String())
	for _, kind := range []string{"backup", "export"} {
		artifact := filepath.Join(t.TempDir(), kind+".lzug")
		request := BackendRequest{Command: kind + "-package-create", Arguments: map[string]any{"recipient_key_fingerprint": fingerprint}}
		_, _, failure := writeProtectedArtifact(context.Background(), artifact, identity.Recipient(), fingerprint, func(writer io.Writer) (BackendResponse, int, error) {
			return transport.Produce(context.Background(), request, writer)
		})
		if failure != nil {
			t.Fatalf("%s create failed: %+v", kind, failure)
		}
		artifactType := "backup"
		if kind == "export" {
			artifactType = "full_export"
		}
		request = BackendRequest{Command: "artifact-package-verify", Arguments: map[string]any{"artifact_type": artifactType}}
		_, _, failure = consumeProtectedArtifact(artifact, identity, fingerprint, func(reader io.Reader) (BackendResponse, int, error) {
			return transport.Consume(context.Background(), request, reader)
		})
		if failure != nil {
			t.Fatalf("%s verify failed: %+v", kind, failure)
		}
		if kind == "backup" {
			request = BackendRequest{Command: "backup-package-restore", Arguments: map[string]any{"replace": true, "safety_artifact": artifact, "recipient_key_fingerprint": fingerprint}}
			_, _, failure = consumeProtectedArtifact(artifact, identity, fingerprint, func(reader io.Reader) (BackendResponse, int, error) {
				return transport.Consume(context.Background(), request, reader)
			})
			if failure != nil {
				t.Fatalf("restore failed: %+v", failure)
			}
		}
	}
}
