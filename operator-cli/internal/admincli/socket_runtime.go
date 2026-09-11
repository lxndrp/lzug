package admincli

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

const maxBackendOutput = 1024 * 1024

type RuntimeErrorKind string

const (
	RuntimeEngineUnavailable RuntimeErrorKind = "engine_unavailable"
	RuntimeEngineFailed      RuntimeErrorKind = "engine_invocation_failed"
	RuntimeProtocol          RuntimeErrorKind = "protocol_incompatible"
	RuntimeRelease           RuntimeErrorKind = "release_artifact_unverified"
)

type RuntimeError struct{ Kind RuntimeErrorKind }

func (e *RuntimeError) Error() string { return string(e.Kind) }

func parseBackendResponse(payload []byte) (BackendResponse, error) {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var response BackendResponse
	if err := decoder.Decode(&response); err != nil {
		return BackendResponse{}, err
	}
	if err := ensureJSONEnd(decoder); err != nil {
		return BackendResponse{}, err
	}
	if response.Version != ProtocolVersion {
		return BackendResponse{}, fmt.Errorf("unsupported backend protocol")
	}
	if response.OK && len(response.Result) == 0 {
		return BackendResponse{}, fmt.Errorf("missing backend result")
	}
	return response, nil
}

type limitedWriter struct {
	Writer    io.Writer
	Remaining int
}

func (writer *limitedWriter) Write(payload []byte) (int, error) {
	if len(payload) > writer.Remaining {
		return 0, fmt.Errorf("socket output exceeds limit")
	}
	written, err := writer.Writer.Write(payload)
	writer.Remaining -= written
	return written, err
}
