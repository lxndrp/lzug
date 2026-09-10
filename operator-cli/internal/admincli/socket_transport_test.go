package admincli

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

const testSocketJob = "11111111-1111-4111-8111-111111111111"
const testSocketCorrelation = "22222222-2222-4222-8222-222222222222"

func socketTestServer(t *testing.T, serve func(net.Conn)) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("Unix pathname sockets")
	}
	// Keep below Unix sockaddr path limits, including macOS's long TempDir root.
	directory, err := os.MkdirTemp("/tmp", "lzug-go-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(directory) })
	path := filepath.Join(directory, "admin.sock")
	listener, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = listener.Close() })
	done := make(chan struct{})
	go func() {
		defer close(done)
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		defer connection.Close()
		_ = connection.SetDeadline(time.Now().Add(3 * time.Second))
		serve(connection)
	}()
	t.Cleanup(func() {
		_ = listener.Close()
		select {
		case <-done:
		case <-time.After(4 * time.Second):
			t.Error("socket server did not stop")
		}
	})
	return path
}

func testWriteEnvelope(t *testing.T, connection net.Conn, envelope socketEnvelope) {
	t.Helper()
	payload, err := json.Marshal(envelope)
	if err != nil {
		t.Error(err)
		return
	}
	if err := writeSocketFrame(connection, payload); err != nil {
		t.Error(err)
	}
}

func testSocketHello(t *testing.T, connection net.Conn) {
	t.Helper()
	hello, err := readSocketFrame(connection)
	if err != nil || hello.Type != "hello" || hello.Protocol != 1 || hello.Schema != 1 {
		t.Errorf("invalid hello: %v", err)
		return
	}
	testWriteEnvelope(t, connection, socketEnvelope{Type: "hello", Protocol: 1, Schema: 1, JobID: testSocketJob, CorrelationID: testSocketCorrelation})
}

func testSocketRequest(t *testing.T, connection net.Conn) BackendRequest {
	t.Helper()
	var header [4]byte
	if _, err := io.ReadFull(connection, header[:]); err != nil {
		t.Error(err)
		return BackendRequest{}
	}
	size := binary.BigEndian.Uint32(header[:])
	if size > maxSocketRequest {
		t.Error("oversized request")
		return BackendRequest{}
	}
	payload := make([]byte, size)
	if _, err := io.ReadFull(connection, payload); err != nil {
		t.Error(err)
		return BackendRequest{}
	}
	var request BackendRequest
	if err := json.Unmarshal(payload, &request); err != nil {
		t.Error(err)
	}
	return request
}

func TestSocketHandshakePrecedesRequestAndReturnsCoreResponse(t *testing.T) {
	path := socketTestServer(t, func(connection net.Conn) {
		testSocketHello(t, connection)
		request := testSocketRequest(t, connection)
		if request.Command != "config" {
			t.Error("wrong command")
		}
		code := 0
		testWriteEnvelope(t, connection, socketEnvelope{Type: "result", JobID: testSocketJob, CorrelationID: testSocketCorrelation,
			Command: "config", Status: "succeeded", ExitCode: &code, Response: json.RawMessage(`{"version":1,"ok":true,"result":{"runtime":{"state":"ready"}}}`)})
	})
	response, code, err := (&SocketTransport{Path: path}).Execute(context.Background(), BackendRequest{Version: 1, Command: "config", Arguments: map[string]any{}})
	if err != nil || code != 0 || !response.OK {
		t.Fatalf("control response failed: %v", err)
	}
}

func TestSocketMismatchNeverSendsControlPayload(t *testing.T) {
	for _, field := range []string{"protocol", "schema", "job_id"} {
		t.Run(field, func(t *testing.T) {
			path := socketTestServer(t, func(connection net.Conn) {
				_, _ = readSocketFrame(connection)
				hello := socketEnvelope{Type: "hello", Protocol: 1, Schema: 1, JobID: testSocketJob, CorrelationID: testSocketCorrelation}
				switch field {
				case "protocol":
					hello.Protocol = 2
				case "schema":
					hello.Schema = 2
				default:
					hello.JobID = "secret"
				}
				testWriteEnvelope(t, connection, hello)
				var extra [1]byte
				if n, _ := connection.Read(extra[:]); n != 0 {
					t.Error("request sent after incompatible handshake")
				}
			})
			_, _, err := (&SocketTransport{Path: path}).Execute(context.Background(), BackendRequest{Version: 1, Command: "bootstrap", Arguments: map[string]any{"email": "secret"}})
			var failure *SocketTransportError
			if !errors.As(err, &failure) || failure.Phase != "handshake" || failure.OutcomeUnknown {
				t.Fatalf("unsafe mismatch error: %v", err)
			}
			if strings.Contains(err.Error(), "secret") {
				t.Fatal("payload leaked")
			}
		})
	}
}

func TestSocketResultLossKeepsIDsAndDoesNotRetry(t *testing.T) {
	path := socketTestServer(t, func(connection net.Conn) {
		testSocketHello(t, connection)
		testSocketRequest(t, connection)
	})
	_, _, err := (&SocketTransport{Path: path}).Execute(context.Background(), BackendRequest{Version: 1, Command: "bootstrap"})
	var failure *SocketTransportError
	if !errors.As(err, &failure) || !failure.OutcomeUnknown || failure.JobID != testSocketJob || failure.CorrelationID != testSocketCorrelation {
		t.Fatalf("lost result lacks recovery evidence: %v", err)
	}
	projected := runtimeFailure(err)
	if projected.Details["job_id"] != testSocketJob || projected.Phase != "transfer" {
		t.Fatal("CLI lost technical evidence")
	}
}

func TestSocketCancellationAndAbsoluteDeadline(t *testing.T) {
	for _, afterRequest := range []bool{false, true} {
		path := socketTestServer(t, func(connection net.Conn) {
			if afterRequest {
				testSocketHello(t, connection)
				testSocketRequest(t, connection)
			} else {
				_, _ = readSocketFrame(connection)
			}
			var extra [1]byte
			_, _ = connection.Read(extra[:])
		})
		start := time.Now()
		_, _, err := (&SocketTransport{Path: path, Timeout: 50 * time.Millisecond}).Execute(context.Background(), BackendRequest{Version: 1, Command: "config"})
		var failure *SocketTransportError
		if !errors.As(err, &failure) || failure.OutcomeUnknown != afterRequest || time.Since(start) > time.Second {
			t.Fatalf("deadline failed: %v", err)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, _, err := (&SocketTransport{Path: "/missing"}).Execute(ctx, BackendRequest{Version: 1})
	if err == nil {
		t.Fatal("cancelled context accepted")
	}
}

func TestSocketMalformedAndOversizedResultsFailSafely(t *testing.T) {
	for _, payload := range [][]byte{nil, []byte(`null`), []byte(`{"type":"result","unknown":"secret"}`), []byte(`{} {}`)} {
		var encoded bytes.Buffer
		_ = writeSocketFrame(&encoded, payload)
		if _, err := readSocketFrame(&encoded); err == nil {
			t.Error("malformed frame accepted")
		}
	}
	var oversized bytes.Buffer
	_ = binary.Write(&oversized, binary.BigEndian, uint32(maxBackendOutput+1))
	if _, err := readSocketFrame(&oversized); err == nil {
		t.Fatal("oversized result accepted")
	}
	path := socketTestServer(t, func(connection net.Conn) {
		testSocketHello(t, connection)
		testSocketRequest(t, connection)
		code := 0
		testWriteEnvelope(t, connection, socketEnvelope{Type: "result", JobID: testSocketJob, CorrelationID: testSocketCorrelation,
			Command: "config", Status: "succeeded", ExitCode: &code, Response: json.RawMessage(`{"version":1,"ok":false,"error":{"class":"secret","message":"secret"}}`)})
	})
	_, _, err := (&SocketTransport{Path: path}).Execute(context.Background(), BackendRequest{Version: 1, Command: "config"})
	if err == nil || strings.Contains(err.Error(), "secret") {
		t.Fatal("invalid result was accepted or leaked")
	}
}

func TestSocketWriterRejectsOversizedPayloadBeforeWriting(t *testing.T) {
	var destination bytes.Buffer
	if err := writeSocketFrame(&destination, make([]byte, maxBackendOutput+1)); err == nil {
		t.Fatal("oversized frame accepted")
	}
	if destination.Len() != 0 {
		t.Fatal("rejected frame was partially transmitted")
	}
}

// TestSocketLive is invoked by the Linux backend suite against its real listener
// and database. All CLI package unit tests remain independent of Python.
func TestSocketLive(t *testing.T) {
	path := os.Getenv("LZUG_SOCKET_TEST_PATH")
	if path == "" {
		t.Skip("run through backend.tests.test_admin_socket")
	}
	factory := &SocketRuntimeFactory{Path: path}
	transport := factory.Transport(EffectiveConfig{})
	response, code, err := transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "bootstrap", Arguments: map[string]any{"email": "oberon@demo.lzug.invalid"}})
	if err != nil || code != 0 || !response.OK {
		t.Fatal("real Linux mutation failed")
	}
	response, code, err = transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "config", Arguments: map[string]any{}})
	if err != nil || code != 0 || !response.OK || !bytes.Contains(response.Result, []byte(`"ready"`)) {
		t.Fatal("real Linux status failed")
	}
	_, _, err = transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "upgrade", Arguments: map[string]any{}})
	var failure *SocketTransportError
	if !errors.As(err, &failure) || failure.Code != "command_unsupported" || failure.OutcomeUnknown {
		t.Fatal("migration activated through control adapter")
	}
	response, code, err = transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "socket-job-status", Arguments: map[string]any{"job_id": failure.JobID}})
	if err != nil || code != 0 || !response.OK || !bytes.Contains(response.Result, []byte(`"rejected"`)) {
		t.Fatal("job lookup failed")
	}
}
