package admincli

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"time"
)

const socketDataTag uint32 = 1 << 31
const maxSocketData = 64 * 1024
const maxSocketStream int64 = 1024 * 1024 * 1024

// Produce streams directly into the caller's local age writer. Only a verified
// stream terminator AND successful result permit the caller to publish its file.
func (transport *SocketTransport) Produce(ctx context.Context, request BackendRequest, target io.Writer) (BackendResponse, int, error) {
	return transport.artifact(ctx, request, target, nil)
}

// Consume reads through authenticated age EOF before sending the terminator.
// A source error closes the connection without authorizing package execution.
// Callers own source/target and must provide cancellable or finite local I/O;
// this adapter never leaves detached goroutines reading or writing their streams.
func (transport *SocketTransport) Consume(ctx context.Context, request BackendRequest, source io.Reader) (BackendResponse, int, error) {
	return transport.artifact(ctx, request, nil, source)
}

func (transport *SocketTransport) artifact(ctx context.Context, request BackendRequest, target io.Writer, source io.Reader) (BackendResponse, int, error) {
	if !validSocketArtifact(request, target != nil) || target == nil && source == nil {
		return BackendResponse{}, ExitEngineFailed, &SocketTransportError{Phase: "validation", Code: "request_invalid"}
	}
	request.Version = socketSchema
	session, err := transport.open(ctx, request, 5*time.Minute)
	if err != nil {
		return BackendResponse{}, ExitEngineFailed, err
	}
	defer session.close()
	ready, err := readSocketFrame(session.connection)
	if err != nil {
		return session.fail()
	}
	if ready.Type == "error" || ready.Type == "result" {
		response, code, failure := session.result(ready, request)
		if failure == nil && response.OK {
			return session.fail()
		}
		return response, code, failure
	}
	direction := "upload"
	if target != nil {
		direction = "download"
	}
	if ready.Type != "stream-ready" || ready.Direction != direction || ready.JobID != session.failure.JobID || ready.CorrelationID != session.failure.CorrelationID || ready.MaxDataBytes <= 0 || ready.MaxDataBytes > maxSocketData || ready.MaxStreamBytes <= 0 || ready.MaxStreamBytes > maxSocketStream {
		return session.fail()
	}
	if target != nil {
		var terminal *socketEnvelope
		terminal, err = receiveSocketArtifact(ctx, session.connection, target, ready)
		if err != nil {
			return session.fail()
		}
		if terminal != nil {
			// A backend failure may interrupt production, but cannot turn a partial
			// stream into success, even when wrapped in a well-formed result.
			response, code, failure := session.result(*terminal, request)
			if failure == nil && response.OK {
				return session.fail()
			}
			return response, code, failure
		}
	} else {
		if err = sendSocketArtifact(ctx, session.connection, source, ready); err != nil {
			return session.fail()
		}
		if err = session.connection.(*net.UnixConn).CloseWrite(); err != nil {
			return session.fail()
		}
	}
	result, err := readSocketFrame(session.connection)
	if err != nil {
		return session.fail()
	}
	response, code, failure := session.result(result, request)
	if failure != nil {
		return response, code, failure
	}
	var extra [1]byte
	if n, err := session.connection.Read(extra[:]); n != 0 || err != io.EOF {
		return session.fail()
	}
	return response, code, nil
}

func validSocketArtifact(request BackendRequest, produce bool) bool {
	fields := map[string]bool{"recipient_key_fingerprint": true}
	switch request.Command {
	case "backup-package-create", "export-package-create":
		if !produce {
			return false
		}
	case "artifact-package-verify":
		if produce {
			return false
		}
		fields = map[string]bool{"artifact_type": true}
		value, _ := request.Arguments["artifact_type"].(string)
		if value != "backup" && value != "full_export" {
			return false
		}
	case "backup-package-restore":
		if produce {
			return false
		}
		fields["replace"], fields["safety_artifact"] = true, true
		if _, ok := request.Arguments["replace"].(bool); !ok {
			return false
		}
		if value := request.Arguments["safety_artifact"]; value != nil {
			text, ok := value.(string)
			if !ok || len(text) == 0 || len(text) > 4096 {
				return false
			}
		}
	default:
		return false
	}
	if len(fields) != len(request.Arguments) {
		return false
	}
	for key := range request.Arguments {
		if !fields[key] {
			return false
		}
	}
	if fields["recipient_key_fingerprint"] {
		value, _ := request.Arguments["recipient_key_fingerprint"].(string)
		if !validFingerprint(value) {
			return false
		}
	}
	return true
}

func sendSocketArtifact(ctx context.Context, connection net.Conn, source io.Reader, ready socketEnvelope) error {
	buffer := make([]byte, ready.MaxDataBytes)
	digest := sha256.New()
	var count int64
	empty := 0
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		n, err := source.Read(buffer)
		if n < 0 || n > len(buffer) {
			return errors.New("invalid source read")
		}
		if n > 0 {
			empty = 0
			if int64(n) > ready.MaxStreamBytes-count {
				return errors.New("stream limit exceeded")
			}
			if failure := writeSocketData(connection, buffer[:n]); failure != nil {
				return failure
			}
			_, _ = digest.Write(buffer[:n])
			count += int64(n)
		} else {
			empty++
		}
		if err == io.EOF {
			if count == 0 {
				return errors.New("empty artifact")
			}
			end, _ := json.Marshal(map[string]any{"type": "stream-end", "bytes": count, "sha256": hex.EncodeToString(digest.Sum(nil))})
			return writeSocketFrame(connection, end)
		}
		if err != nil {
			return err
		}
		if empty >= 100 {
			return io.ErrNoProgress
		}
	}
}

func receiveSocketArtifact(ctx context.Context, connection net.Conn, target io.Writer, ready socketEnvelope) (*socketEnvelope, error) {
	digest := sha256.New()
	var count int64
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		data, control, err := readSocketPacket(connection)
		if err != nil {
			return nil, err
		}
		if data != nil {
			if len(data) > ready.MaxDataBytes || int64(len(data)) > ready.MaxStreamBytes-count {
				return nil, errors.New("stream limit exceeded")
			}
			n, err := target.Write(data)
			if err != nil {
				return nil, err
			}
			if n != len(data) {
				return nil, io.ErrShortWrite
			}
			_, _ = digest.Write(data)
			count += int64(n)
			continue
		}
		if control.Type == "error" || control.Type == "result" {
			return &control, nil
		}
		if control.Type != "stream-end" || control.Bytes == nil || *control.Bytes != count || count == 0 || control.SHA256 != hex.EncodeToString(digest.Sum(nil)) {
			return nil, errors.New("incomplete stream")
		}
		return nil, nil
	}
}

func writeSocketData(destination io.Writer, payload []byte) error {
	if len(payload) == 0 || len(payload) > maxSocketData {
		return errors.New("invalid data size")
	}
	var header [4]byte
	binary.BigEndian.PutUint32(header[:], socketDataTag|uint32(len(payload)))
	for _, part := range [][]byte{header[:], payload} {
		for len(part) > 0 {
			n, err := destination.Write(part)
			if err != nil {
				return err
			}
			if n <= 0 || n > len(part) {
				return io.ErrShortWrite
			}
			part = part[n:]
		}
	}
	return nil
}

func readSocketPacket(source io.Reader) ([]byte, socketEnvelope, error) {
	var header [4]byte
	if _, err := io.ReadFull(source, header[:]); err != nil {
		return nil, socketEnvelope{}, err
	}
	encoded := binary.BigEndian.Uint32(header[:])
	size := encoded &^ socketDataTag
	data := encoded&socketDataTag != 0
	if size == 0 || data && size > maxSocketData || !data && size > maxBackendOutput {
		return nil, socketEnvelope{}, fmt.Errorf("invalid socket frame size")
	}
	payload := make([]byte, size)
	if _, err := io.ReadFull(source, payload); err != nil {
		return nil, socketEnvelope{}, err
	}
	if data {
		return payload, socketEnvelope{}, nil
	}
	envelope, err := decodeSocketEnvelope(payload)
	return nil, envelope, err
}
