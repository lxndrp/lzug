package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
)

const artifactStreamProtocol = 2

type ContainerArtifactTransport struct {
	Config   EffectiveConfig
	Resolver EngineResolver
}

func (transport *ContainerArtifactTransport) Produce(
	ctx context.Context,
	request BackendRequest,
	target io.Writer,
) (BackendResponse, int, error) {
	request.Version = artifactStreamProtocol
	payload, err := json.Marshal(request)
	if err != nil {
		return BackendResponse{}, ExitUnexpected, &RuntimeError{Kind: RuntimeEngineFailed}
	}
	payload = append(payload, '\n')
	command, failure := transport.command(ctx, "produce")
	if failure != nil {
		return BackendResponse{}, ExitEngineUnavailable, failure
	}
	var control bytes.Buffer
	command.Stdin = bytes.NewReader(payload)
	command.Stdout = target
	command.Stderr = &limitedWriter{Writer: &control, Remaining: maxBackendOutput}
	runError := command.Run()
	return decodeArtifactControl(control.Bytes(), runError)
}

func (transport *ContainerArtifactTransport) Consume(
	ctx context.Context,
	request BackendRequest,
	source io.Reader,
) (BackendResponse, int, error) {
	request.Version = artifactStreamProtocol
	payload, err := json.Marshal(request)
	if err != nil {
		return BackendResponse{}, ExitUnexpected, &RuntimeError{Kind: RuntimeEngineFailed}
	}
	payload = append(payload, '\n')
	command, failure := transport.command(ctx, "consume")
	if failure != nil {
		return BackendResponse{}, ExitEngineUnavailable, failure
	}
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdin = io.MultiReader(bytes.NewReader(payload), source)
	command.Stdout = &limitedWriter{Writer: &stdout, Remaining: maxBackendOutput}
	command.Stderr = &limitedWriter{Writer: &stderr, Remaining: maxBackendOutput}
	runError := command.Run()
	if stderr.Len() != 0 {
		return BackendResponse{}, ExitEngineFailed, &RuntimeError{Kind: RuntimeEngineFailed}
	}
	return decodeArtifactControl(stdout.Bytes(), runError)
}

func (transport *ContainerArtifactTransport) command(
	ctx context.Context,
	mode string,
) (*exec.Cmd, error) {
	engine, err := transport.Resolver.Resolve(transport.Config.Engine.Value)
	if err != nil {
		return nil, &RuntimeError{Kind: RuntimeEngineUnavailable}
	}
	return exec.CommandContext(
		ctx,
		engine,
		"exec",
		"--interactive",
		transport.Config.Container.Value,
		"python",
		"-m",
		"backend.artifact_stream",
		"--protocol",
		fmt.Sprint(artifactStreamProtocol),
		mode,
	), nil
}

func decodeArtifactControl(payload []byte, runError error) (BackendResponse, int, error) {
	exitCode := ExitOK
	if runError != nil {
		var exitError *exec.ExitError
		if !errorsAs(runError, &exitError) {
			return BackendResponse{}, ExitEngineFailed, &RuntimeError{Kind: RuntimeEngineFailed}
		}
		exitCode = exitError.ExitCode()
	}
	var response BackendResponse
	if len(payload) == 0 || json.Unmarshal(payload, &response) != nil || response.Version != ProtocolVersion {
		return BackendResponse{}, ExitProtocolIncompatible, &RuntimeError{Kind: RuntimeProtocol}
	}
	return response, exitCode, nil
}

// Kept as a variable so tests can exercise process failures without wrapping os/exec.
var errorsAs = func(err error, target any) bool {
	return errors.As(err, target)
}
