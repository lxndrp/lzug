package admincli

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"path/filepath"
	"regexp"
	"time"
)

const socketProtocol = 1
const socketSchema = 1
const maxSocketRequest = 64 * 1024

var socketID = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

// SocketTransportError contains only technical evidence, never system errors or payloads.
// OutcomeUnknown means the request may have executed; callers must never retry it automatically.
type SocketTransportError struct {
	Phase          string
	Code           string
	JobID          string
	CorrelationID  string
	OutcomeUnknown bool
}

func (e *SocketTransportError) Error() string { return "Admin socket request failed" }

// SocketRuntimeFactory explicitly binds control and artifact requests to one socket.
// Release activation and regular CLI selection remain separate integration work.
type SocketRuntimeFactory struct {
	Path    string
	Timeout time.Duration
}

func (factory *SocketRuntimeFactory) Transport(_ EffectiveConfig) Transport {
	return &SocketTransport{Path: factory.Path, Timeout: factory.Timeout}
}

func (factory *SocketRuntimeFactory) ArtifactTransport(_ EffectiveConfig) ArtifactTransport {
	return &SocketTransport{Path: factory.Path, Timeout: factory.Timeout}
}

func (factory *SocketRuntimeFactory) ReleaseInspector(_ EffectiveConfig) ReleaseInspector {
	return unsupportedSocketRelease{}
}

type unsupportedSocketRelease struct{}

func (unsupportedSocketRelease) Target(context.Context, BuildInfo) (map[string]any, error) {
	return nil, &SocketTransportError{Phase: "validation", Code: "command_unsupported"}
}

// SocketTransport sends one control request directly to a pathname Unix socket.
// There is no subprocess, network listener, fallback transport or automatic retry.
type SocketTransport struct {
	Path    string
	Timeout time.Duration
}

type socketEnvelope struct {
	Type           string          `json:"type"`
	Protocol       int             `json:"protocol,omitempty"`
	Schema         int             `json:"schema,omitempty"`
	JobID          string          `json:"job_id"`
	CorrelationID  string          `json:"correlation_id"`
	Limits         json.RawMessage `json:"limits,omitempty"`
	Command        string          `json:"command,omitempty"`
	Phase          string          `json:"phase,omitempty"`
	Status         string          `json:"status,omitempty"`
	Delivery       string          `json:"delivery,omitempty"`
	Code           string          `json:"code,omitempty"`
	ExitCode       *int            `json:"exit_code,omitempty"`
	Response       json.RawMessage `json:"response,omitempty"`
	Direction      string          `json:"direction,omitempty"`
	MaxDataBytes   int             `json:"max_data_bytes,omitempty"`
	MaxStreamBytes int64           `json:"max_stream_bytes,omitempty"`
	Bytes          *int64          `json:"bytes,omitempty"`
	SHA256         string          `json:"sha256,omitempty"`
}

func (transport *SocketTransport) Execute(ctx context.Context, request BackendRequest) (BackendResponse, int, error) {
	session, err := transport.open(ctx, request, 30*time.Second)
	if err != nil {
		return BackendResponse{}, ExitEngineFailed, err
	}
	defer session.close()
	result, err := readSocketFrame(session.connection)
	if err != nil {
		return session.fail()
	}
	return session.result(result, request)
}

type socketSession struct {
	connection net.Conn
	failure    *SocketTransportError
	close      func()
}

func (session *socketSession) fail() (BackendResponse, int, error) {
	return BackendResponse{}, ExitEngineFailed, session.failure
}

func (transport *SocketTransport) open(ctx context.Context, request BackendRequest, defaultTimeout time.Duration) (*socketSession, error) {
	failure := &SocketTransportError{Phase: "connection", Code: "connection_failed"}
	if !filepath.IsAbs(transport.Path) || bytes.IndexByte([]byte(transport.Path), 0) >= 0 {
		return nil, failure
	}
	payload, err := json.Marshal(request)
	if err != nil || len(payload) > maxSocketRequest {
		failure.Phase, failure.Code = "validation", "request_invalid"
		return nil, failure
	}
	timeout := transport.Timeout
	if timeout == 0 {
		timeout = defaultTimeout
	}
	if timeout < 0 || timeout > time.Hour {
		failure.Phase, failure.Code = "validation", "request_invalid"
		return nil, failure
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	connection, err := (&net.Dialer{}).DialContext(ctx, "unix", transport.Path)
	if err != nil {
		cancel()
		return nil, failure
	}
	stop := context.AfterFunc(ctx, func() { _ = connection.Close() })
	session := &socketSession{connection: connection, failure: failure, close: func() { stop(); cancel(); _ = connection.Close() }}
	failed := func() (*socketSession, error) { session.close(); return nil, failure }
	deadline, _ := ctx.Deadline()
	if err = connection.SetDeadline(deadline); err != nil {
		return failed()
	}
	failure.Phase, failure.Code = "handshake", "handshake_failed"
	hello, _ := json.Marshal(map[string]any{"type": "hello", "protocol": socketProtocol, "schema": socketSchema})
	if err = writeSocketFrame(connection, hello); err != nil {
		return failed()
	}
	accepted, err := readSocketFrame(connection)
	if err != nil {
		return failed()
	}
	if accepted.Type == "error" {
		setSocketError(failure, accepted)
		return failed()
	}
	if accepted.Type != "hello" || accepted.Protocol != socketProtocol || accepted.Schema != socketSchema ||
		!socketID.MatchString(accepted.JobID) || !socketID.MatchString(accepted.CorrelationID) {
		failure.Code = "version_incompatible"
		return failed()
	}
	failure.JobID, failure.CorrelationID = accepted.JobID, accepted.CorrelationID
	failure.Phase, failure.Code = "transfer", "result_unavailable"
	failure.OutcomeUnknown = true
	if err = writeSocketFrame(connection, payload); err != nil {
		return failed()
	}
	return session, nil
}

func (session *socketSession) result(result socketEnvelope, request BackendRequest) (BackendResponse, int, error) {
	failure := session.failure
	fail := session.fail
	if result.JobID != failure.JobID || result.CorrelationID != failure.CorrelationID {
		return fail()
	}
	if result.Type == "error" {
		setSocketError(failure, result)
		return fail()
	}
	if result.Type != "result" || result.ExitCode == nil || result.Command != request.Command {
		return fail()
	}
	response, err := parseBackendResponse(result.Response)
	if err != nil || response.OK && response.Error != nil || !response.OK && response.Error == nil {
		return fail()
	}
	code := *result.ExitCode
	if response.OK && code != ExitOK && code != 30 && code != 31 || !response.OK && (code <= 0 || code > 255) ||
		response.OK && result.Status != "succeeded" || !response.OK && result.Status != "failed" {
		return fail()
	}
	return response, code, nil
}

func setSocketError(failure *SocketTransportError, envelope socketEnvelope) {
	// Never reflect arbitrary remote strings into local errors, including IDs.
	allowed := map[string]string{
		"version_incompatible": "handshake", "authorization_failed": "authorization",
		"request_invalid": "validation", "frame_invalid": "validation",
		"command_unsupported": "validation", "socket_stopping": "lifecycle",
		"result_too_large": "transfer",
		"artifact_busy":    "lifecycle", "lifecycle_conflict": "lifecycle",
		"artifact_cleanup_required": "lifecycle",
		"stream_frame_invalid":      "transfer", "stream_incomplete": "transfer",
		"stream_limit_exceeded": "transfer",
	}
	if phase, ok := allowed[envelope.Code]; ok && envelope.Phase == phase {
		failure.Phase, failure.Code = phase, envelope.Code
	}
	if socketID.MatchString(envelope.JobID) && socketID.MatchString(envelope.CorrelationID) {
		failure.JobID, failure.CorrelationID = envelope.JobID, envelope.CorrelationID
	}
	// Only an explicit rejection proves no application execution began.
	if envelope.Status == "rejected" {
		failure.OutcomeUnknown = false
	}
}

func writeSocketFrame(destination io.Writer, payload []byte) error {
	if len(payload) == 0 || len(payload) > maxBackendOutput {
		return fmt.Errorf("invalid socket frame size")
	}
	frame := make([]byte, 4+len(payload))
	binary.BigEndian.PutUint32(frame, uint32(len(payload)))
	copy(frame[4:], payload)
	for len(frame) > 0 {
		n, err := destination.Write(frame)
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrShortWrite
		}
		frame = frame[n:]
	}
	return nil
}

func readSocketFrame(source io.Reader) (socketEnvelope, error) {
	var header [4]byte
	if _, err := io.ReadFull(source, header[:]); err != nil {
		return socketEnvelope{}, err
	}
	size := binary.BigEndian.Uint32(header[:])
	if size == 0 || size > maxBackendOutput {
		return socketEnvelope{}, fmt.Errorf("invalid socket frame size")
	}
	payload := make([]byte, size)
	if _, err := io.ReadFull(source, payload); err != nil {
		return socketEnvelope{}, err
	}
	return decodeSocketEnvelope(payload)
}

func decodeSocketEnvelope(payload []byte) (socketEnvelope, error) {
	if err := uniqueSocketJSON(json.NewDecoder(bytes.NewReader(payload)), 0); err != nil {
		return socketEnvelope{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var envelope socketEnvelope
	if err := decoder.Decode(&envelope); err != nil {
		return socketEnvelope{}, err
	}
	if envelope.Type == "" {
		return socketEnvelope{}, fmt.Errorf("missing socket frame type")
	}
	return envelope, ensureJSONEnd(decoder)
}

func uniqueSocketJSON(decoder *json.Decoder, depth int) error {
	if depth > 64 {
		return fmt.Errorf("socket JSON nesting limit")
	}
	value, err := decoder.Token()
	if err != nil {
		return err
	}
	delimiter, compound := value.(json.Delim)
	if !compound {
		return nil
	}
	if delimiter != '{' && delimiter != '[' {
		return fmt.Errorf("invalid JSON delimiter")
	}
	keys := map[string]bool{}
	for decoder.More() {
		if delimiter == '{' {
			key, err := decoder.Token()
			if err != nil {
				return err
			}
			name, ok := key.(string)
			if !ok || keys[name] {
				return fmt.Errorf("duplicate JSON key")
			}
			keys[name] = true
		}
		if err := uniqueSocketJSON(decoder, depth+1); err != nil {
			return err
		}
	}
	_, err = decoder.Token()
	return err
}
