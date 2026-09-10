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

// SocketRuntimeFactory is the explicit, injectable control assembly. Artifact and
// release activation support belong to the subsequent transport migration issues.
type SocketRuntimeFactory struct {
	Path    string
	Timeout time.Duration
}

func (factory *SocketRuntimeFactory) Transport(_ EffectiveConfig) Transport {
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
	Type          string          `json:"type"`
	Protocol      int             `json:"protocol,omitempty"`
	Schema        int             `json:"schema,omitempty"`
	JobID         string          `json:"job_id"`
	CorrelationID string          `json:"correlation_id"`
	Limits        json.RawMessage `json:"limits,omitempty"`
	Command       string          `json:"command,omitempty"`
	Phase         string          `json:"phase,omitempty"`
	Status        string          `json:"status,omitempty"`
	Delivery      string          `json:"delivery,omitempty"`
	Code          string          `json:"code,omitempty"`
	ExitCode      *int            `json:"exit_code,omitempty"`
	Response      json.RawMessage `json:"response,omitempty"`
}

func (transport *SocketTransport) Execute(ctx context.Context, request BackendRequest) (BackendResponse, int, error) {
	failure := &SocketTransportError{Phase: "connection", Code: "connection_failed"}
	fail := func() (BackendResponse, int, error) { return BackendResponse{}, ExitEngineFailed, failure }
	if !filepath.IsAbs(transport.Path) || bytes.IndexByte([]byte(transport.Path), 0) >= 0 {
		return fail()
	}
	payload, err := json.Marshal(request)
	if err != nil || len(payload) > maxSocketRequest {
		failure.Phase, failure.Code = "validation", "request_invalid"
		return fail()
	}
	timeout := transport.Timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}
	if timeout < 0 || timeout > time.Hour {
		failure.Phase, failure.Code = "validation", "request_invalid"
		return fail()
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	connection, err := (&net.Dialer{}).DialContext(ctx, "unix", transport.Path)
	if err != nil {
		return fail()
	}
	defer connection.Close()
	stop := context.AfterFunc(ctx, func() { _ = connection.Close() })
	defer stop()
	deadline, _ := ctx.Deadline()
	if err = connection.SetDeadline(deadline); err != nil {
		return fail()
	}
	failure.Phase, failure.Code = "handshake", "handshake_failed"
	hello, _ := json.Marshal(map[string]any{"type": "hello", "protocol": socketProtocol, "schema": socketSchema})
	if err = writeSocketFrame(connection, hello); err != nil {
		return fail()
	}
	accepted, err := readSocketFrame(connection)
	if err != nil {
		return fail()
	}
	if accepted.Type == "error" {
		setSocketError(failure, accepted)
		return fail()
	}
	if accepted.Type != "hello" || accepted.Protocol != socketProtocol || accepted.Schema != socketSchema ||
		!socketID.MatchString(accepted.JobID) || !socketID.MatchString(accepted.CorrelationID) {
		failure.Code = "version_incompatible"
		return fail()
	}
	failure.JobID, failure.CorrelationID = accepted.JobID, accepted.CorrelationID
	failure.Phase, failure.Code = "transfer", "result_unavailable"
	// A partial write or lost result is ambiguous. Do not reconnect or replay.
	failure.OutcomeUnknown = true
	if err = writeSocketFrame(connection, payload); err != nil {
		return fail()
	}
	result, err := readSocketFrame(connection)
	if err != nil || result.JobID != accepted.JobID || result.CorrelationID != accepted.CorrelationID {
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
