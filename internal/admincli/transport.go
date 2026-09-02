package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"regexp"
	"strings"
)

const maxBackendOutput = 1024 * 1024

var canonicalReleaseImagePattern = regexp.MustCompile(`^ghcr\.io/lxndrp/lzug@sha256:[0-9a-f]{64}$`)

type RuntimeErrorKind string

const (
	RuntimeEngineUnavailable RuntimeErrorKind = "engine_unavailable"
	RuntimeEngineFailed      RuntimeErrorKind = "engine_invocation_failed"
	RuntimeProtocol          RuntimeErrorKind = "protocol_incompatible"
	RuntimeRelease           RuntimeErrorKind = "release_artifact_unverified"
)

type RuntimeError struct {
	Kind RuntimeErrorKind
}

func (e *RuntimeError) Error() string {
	return string(e.Kind)
}

type EngineResolver interface {
	Resolve(string) (string, error)
}

type PATHEngineResolver struct{}

func (PATHEngineResolver) Resolve(preferred string) (string, error) {
	if preferred != "" && preferred != "auto" {
		return exec.LookPath(preferred)
	}
	for _, candidate := range []string{"docker", "podman"} {
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	return "", exec.ErrNotFound
}

type ContainerRuntimeFactory struct {
	Resolver EngineResolver
}

func NewContainerRuntimeFactory() *ContainerRuntimeFactory {
	return &ContainerRuntimeFactory{Resolver: PATHEngineResolver{}}
}

func (factory *ContainerRuntimeFactory) Transport(config EffectiveConfig) Transport {
	return &ContainerTransport{Config: config, Resolver: factory.Resolver}
}

func (factory *ContainerRuntimeFactory) ArtifactTransport(config EffectiveConfig) ArtifactTransport {
	return &ContainerArtifactTransport{Config: config, Resolver: factory.Resolver}
}

func (factory *ContainerRuntimeFactory) ReleaseInspector(config EffectiveConfig) ReleaseInspector {
	return &ContainerReleaseInspector{Config: config, Resolver: factory.Resolver}
}

type ContainerTransport struct {
	Config   EffectiveConfig
	Resolver EngineResolver
}

func (transport *ContainerTransport) Execute(
	ctx context.Context,
	request BackendRequest,
) (BackendResponse, int, error) {
	if err := ctx.Err(); err != nil {
		return BackendResponse{}, ExitInterrupted, err
	}
	engine, err := transport.Resolver.Resolve(transport.Config.Engine.Value)
	if err != nil {
		return BackendResponse{}, ExitEngineUnavailable, &RuntimeError{Kind: RuntimeEngineUnavailable}
	}
	payload, err := json.Marshal(request)
	if err != nil {
		return BackendResponse{}, ExitUnexpected, &RuntimeError{Kind: RuntimeEngineFailed}
	}
	payload = append(payload, '\n')
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command := exec.CommandContext(
		ctx,
		engine,
		"exec",
		"--interactive",
		transport.Config.Container.Value,
		"python",
		"-m",
		"backend.admin",
		"--protocol",
		fmt.Sprint(ProtocolVersion),
	)
	command.Stdin = bytes.NewReader(payload)
	command.Stdout = &limitedWriter{Writer: &stdout, Remaining: maxBackendOutput}
	command.Stderr = &limitedWriter{Writer: &stderr, Remaining: maxBackendOutput}
	runError := command.Run()
	if ctx.Err() != nil {
		return BackendResponse{}, ExitInterrupted, ctx.Err()
	}
	exitCode := 0
	if runError != nil {
		var exitError *exec.ExitError
		if !errors.As(runError, &exitError) {
			return BackendResponse{}, ExitEngineFailed, &RuntimeError{Kind: RuntimeEngineFailed}
		}
		exitCode = exitError.ExitCode()
	}
	if stdout.Len() == 0 {
		return BackendResponse{}, ExitEngineFailed, &RuntimeError{Kind: RuntimeEngineFailed}
	}
	response, parseError := parseBackendResponse(stdout.Bytes())
	if parseError != nil {
		return BackendResponse{}, ExitProtocolIncompatible, &RuntimeError{Kind: RuntimeProtocol}
	}
	if response.OK && response.Error != nil || !response.OK && response.Error == nil {
		return BackendResponse{}, ExitProtocolIncompatible, &RuntimeError{Kind: RuntimeProtocol}
	}
	if response.OK && exitCode != ExitOK && exitCode != 30 && exitCode != 31 {
		return BackendResponse{}, ExitProtocolIncompatible, &RuntimeError{Kind: RuntimeProtocol}
	}
	if !response.OK && exitCode == ExitOK {
		return BackendResponse{}, ExitProtocolIncompatible, &RuntimeError{Kind: RuntimeProtocol}
	}
	return response, exitCode, nil
}

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
		return 0, fmt.Errorf("process output exceeds limit")
	}
	written, err := writer.Writer.Write(payload)
	writer.Remaining -= written
	return written, err
}

type ContainerReleaseInspector struct {
	Config   EffectiveConfig
	Resolver EngineResolver
}

func (inspector *ContainerReleaseInspector) Target(ctx context.Context, build BuildInfo) (map[string]any, error) {
	if build.Tag == "" || build.Version != strings.TrimPrefix(build.Tag, "v") {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	engine, err := inspector.Resolver.Resolve(inspector.Config.Engine.Value)
	if err != nil {
		return nil, &RuntimeError{Kind: RuntimeEngineUnavailable}
	}
	container := inspector.Config.Container.Value
	imageID, err := commandOutput(ctx, engine, "container", "inspect", "--format", "{{.Image}}", container)
	if err != nil || strings.TrimSpace(imageID) == "" {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	repoDigestsJSON, err := commandOutput(ctx, engine, "image", "inspect", "--format", "{{json .RepoDigests}}", strings.TrimSpace(imageID))
	if err != nil {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	var repoDigests []string
	if json.Unmarshal([]byte(strings.TrimSpace(repoDigestsJSON)), &repoDigests) != nil {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	canonicalImage := ""
	for _, digest := range repoDigests {
		if canonicalReleaseImagePattern.MatchString(digest) {
			canonicalImage = digest
			break
		}
	}
	if canonicalImage == "" {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	labelsJSON, err := commandOutput(ctx, engine, "image", "inspect", "--format", "{{json .Config.Labels}}", strings.TrimSpace(imageID))
	if err != nil {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	var labels map[string]string
	if json.Unmarshal([]byte(strings.TrimSpace(labelsJSON)), &labels) != nil ||
		labels["org.opencontainers.image.source"] != "https://github.com/lxndrp/lzug" ||
		labels["org.opencontainers.image.version"] != build.Version ||
		labels["org.opencontainers.image.revision"] != build.Revision {
		return nil, &RuntimeError{Kind: RuntimeRelease}
	}
	return map[string]any{
		"identity": build.Version,
		"image":    canonicalImage,
		"release":  true,
		"revision": build.Revision,
		"tag":      build.Tag,
	}, nil
}

func commandOutput(ctx context.Context, command string, arguments ...string) (string, error) {
	output, err := exec.CommandContext(ctx, command, arguments...).Output()
	if err != nil {
		return "", err
	}
	return string(output), nil
}
