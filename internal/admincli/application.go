package admincli

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
)

type buildMetadata struct {
	Identity string  `json:"identity"`
	Release  bool    `json:"release"`
	Revision string  `json:"revision"`
	Tag      *string `json:"tag"`
}

func NewApplication(
	registry *Registry,
	build BuildInfo,
	runtime RuntimeFactory,
	config ConfigResolver,
	input Input,
	renderer Renderer,
) *Application {
	return &Application{
		Registry: registry,
		Build:    build,
		Runtime:  runtime,
		Config:   config,
		Input:    input,
		Renderer: renderer,
	}
}

// InteractiveRequested reports whether args select the guided CLI entrypoint.
// It lets the executable leave terminal interrupts to the dialog while direct
// commands keep the process-wide cancellation contract.
func InteractiveRequested(args []string) bool {
	_, remaining, failure := parseGlobalOptions(args)
	return failure == nil && len(remaining) == 1 && remaining[0] == "cli"
}

func (application *Application) Run(ctx context.Context, args []string) int {
	if failure := application.validate(); failure != nil {
		if application.Renderer != nil {
			application.Renderer.Error(GlobalOptions{}, "", failure)
		}
		return failure.ExitCode
	}
	if err := ctx.Err(); err != nil {
		failure := interruptedError()
		application.Renderer.Error(GlobalOptions{JSON: jsonOutputRequested(args)}, "", failure)
		return failure.ExitCode
	}
	if len(args) == 1 && args[0] == "--version" {
		if failure := application.Renderer.Informational(GlobalOptions{}, map[string]any{"version": application.Build.Version}, VersionText(application.Build)+"\n"); failure != nil {
			application.Renderer.Error(GlobalOptions{}, "", failure)
			return failure.ExitCode
		}
		return ExitOK
	}
	if len(args) == 1 && args[0] == "--build-metadata" {
		metadata := BuildMetadata(application.Build)
		encoded, err := json.Marshal(metadata)
		if err != nil {
			failure := unexpectedError()
			application.Renderer.Error(GlobalOptions{}, "", failure)
			return failure.ExitCode
		}
		if failure := application.Renderer.Informational(GlobalOptions{}, metadata, string(encoded)+"\n"); failure != nil {
			application.Renderer.Error(GlobalOptions{}, "", failure)
			return failure.ExitCode
		}
		return ExitOK
	}

	global, remaining, failure := parseGlobalOptions(args)
	if failure != nil {
		application.Renderer.Error(global, "", failure)
		return failure.ExitCode
	}
	if len(remaining) > 0 && remaining[0] == "cli" {
		if global.JSON {
			failure = invalidInvocation("cli cannot be combined with --json")
			application.Renderer.Error(global, "cli", failure)
			return failure.ExitCode
		}
		if global.ForceSet {
			failure = invalidInvocation("cli cannot be combined with --force")
			application.Renderer.Error(global, "cli", failure)
			return failure.ExitCode
		}
		if len(remaining) == 1 {
			return application.RunInteractive(ctx, global)
		}
	}
	if len(remaining) == 1 && remaining[0] == "--version" {
		if global.ForceSet || global.ConfigSet || global.NoConfig || global.EngineSet || global.ContainerSet {
			failure = invalidInvocation("--version cannot be combined with operational options")
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		if failure = application.Renderer.Informational(global, map[string]any{"version": application.Build.Version}, VersionText(application.Build)+"\n"); failure != nil {
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		return ExitOK
	}
	if len(remaining) == 1 && remaining[0] == "--build-metadata" {
		if global.ForceSet || global.ConfigSet || global.NoConfig || global.EngineSet || global.ContainerSet {
			failure = invalidInvocation("--build-metadata cannot be combined with operational options")
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		metadata := BuildMetadata(application.Build)
		if global.JSON {
			if failure = application.Renderer.Informational(global, metadata, ""); failure != nil {
				application.Renderer.Error(global, "", failure)
				return failure.ExitCode
			}
			return ExitOK
		}
		encoded, err := json.Marshal(metadata)
		if err != nil {
			failure = unexpectedError()
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		if failure = application.Renderer.Informational(global, metadata, string(encoded)+"\n"); failure != nil {
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		return ExitOK
	}

	resolved, helpTarget, failure := resolveInvocation(application.Registry, remaining)
	if failure != nil {
		application.Renderer.Error(global, "", failure)
		return failure.ExitCode
	}
	if helpTarget != "" {
		help, found := Help(application.Registry, helpTarget)
		if !found {
			failure = unexpectedError()
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		if failure = application.Renderer.Informational(global, map[string]any{"help": help}, help); failure != nil {
			application.Renderer.Error(global, "", failure)
			return failure.ExitCode
		}
		return ExitOK
	}
	return application.Execute(ctx, resolved.command.Path, resolved.args, global)
}

// Execute invokes a registered command through the same path used by direct CLI
// parsing. A later interactive adapter can therefore reuse validation, request
// preparation, transport, and rendering without duplicating command handlers.
func (application *Application) Execute(
	ctx context.Context,
	path []string,
	args []string,
	global GlobalOptions,
) int {
	command, found := application.Registry.Find(path)
	if !found {
		failure := invalidInvocation("unsupported admin command %q", strings.Join(path, " "))
		application.Renderer.Error(global, "", failure)
		return failure.ExitCode
	}
	values, failure := parseCommandOptions(command, args)
	if failure != nil {
		application.Renderer.Error(global, command.Name(), failure)
		return failure.ExitCode
	}
	if global.ForceSet && !command.Confirmation.Required {
		failure = invalidInvocation("%s does not accept --force", command.Name())
		application.Renderer.Error(global, command.Name(), failure)
		return failure.ExitCode
	}

	config := EffectiveConfig{}
	if command.Transport == ContainerExecTransport || command.UsesConfig {
		config, failure = application.Config.Resolve(global)
		if failure != nil {
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
	}
	if command.Transport == ContainerExecTransport && config.Container.Value == "" {
		failure = invalidInvocation("a container must be set by --container, LZUG_ADMIN_CONTAINER, or configuration file")
		application.Renderer.Error(global, command.Name(), failure)
		return failure.ExitCode
	}

	if command.Confirmation.Required && !global.Force {
		if !application.Input.IsTerminal() {
			failure = &CLIError{
				Class:    "confirmation_required",
				Message:  "This destructive operation requires an interactive confirmation or --force.",
				NextStep: "Review the target and retry with --force only if the ordinary confirmation may be skipped.",
				ExitCode: ExitInvalidInvocation,
			}
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		prompt := command.Confirmation.Prompt(values, config)
		if strings.TrimSpace(prompt) == "" {
			failure = unexpectedError()
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		confirmed, err := application.Input.Confirm(prompt)
		if errors.Is(err, errInputInterrupted) {
			failure = interruptedError()
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		if err != nil || !confirmed {
			failure = &CLIError{
				Class:    "confirmation_declined",
				Message:  "The destructive operation was not confirmed.",
				NextStep: "No administration request was sent; review the target before retrying.",
				ExitCode: ExitInvalidInvocation,
			}
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
	}

	secrets := Values{}
	for _, secret := range command.Secrets {
		value, err := application.Input.ReadSecret(secret.Prompt)
		if errors.Is(err, errInputInterrupted) {
			failure = interruptedError()
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		if err != nil {
			failure = invalidInvocation("%s requires %s", command.Name(), secret.Description)
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		secrets[secret.Name] = value
	}

	application.Renderer.Progress(global, command, "executing", 0)
	if command.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, command.Timeout)
		defer cancel()
	}
	if command.IsLocal() {
		result, localFailure := command.Local(ctx, LocalContext{Registry: application.Registry, Config: config}, values)
		if localFailure != nil {
			application.Renderer.Error(global, command.Name(), localFailure)
			return localFailure.ExitCode
		}
		if failure = application.Renderer.LocalSuccess(global, command, result); failure != nil {
			application.Renderer.Error(global, command.Name(), failure)
			return failure.ExitCode
		}
		application.Renderer.Progress(global, command, "completed", ExitOK)
		return ExitOK
	}

	transport := application.Runtime.Transport(config)
	inspector := application.Runtime.ReleaseInspector(config)
	request, err := command.BuildRequest(ctx, PrepareContext{Build: application.Build, ReleaseInspector: inspector}, values, secrets)
	if err != nil {
		failure = runtimeFailure(err)
		application.Renderer.Error(global, command.Name(), failure)
		return failure.ExitCode
	}
	response, exitCode, err := transport.Execute(ctx, request)
	if err != nil {
		failure = runtimeFailure(err)
		application.Renderer.Error(global, command.Name(), failure)
		return failure.ExitCode
	}
	if failure = application.Renderer.Backend(global, command, response, exitCode); failure != nil {
		return failure.ExitCode
	}
	application.Renderer.Progress(global, command, "completed", exitCode)
	return exitCode
}

func (application *Application) validate() *CLIError {
	if application.Registry == nil || application.Runtime == nil || application.Config == nil || application.Input == nil || application.Renderer == nil {
		return unexpectedError()
	}
	return nil
}

func VersionText(build BuildInfo) string {
	return "lzug-admin " + build.Version
}

func BuildMetadata(build BuildInfo) buildMetadata {
	metadata := buildMetadata{
		Identity: build.Version,
		Release:  build.Tag != "",
		Revision: build.Revision,
	}
	if build.Tag != "" {
		tag := build.Tag
		metadata.Tag = &tag
	}
	return metadata
}

func runtimeFailure(err error) *CLIError {
	if errors.Is(err, context.Canceled) {
		return interruptedError()
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return &CLIError{
			Class:    "timeout",
			Message:  "The administration command exceeded its declared time limit.",
			NextStep: "Inspect the operation state before deciding whether a retry is safe.",
			ExitCode: ExitEngineFailed,
		}
	}
	var runtimeError *RuntimeError
	if errors.As(err, &runtimeError) {
		switch runtimeError.Kind {
		case RuntimeEngineUnavailable:
			return &CLIError{Class: string(runtimeError.Kind), Message: "No supported container engine is available.", NextStep: "Install Docker or Podman, or select the available engine explicitly.", ExitCode: ExitEngineUnavailable}
		case RuntimeEngineFailed:
			return &CLIError{Class: string(runtimeError.Kind), Message: "The local container engine could not execute the administration request.", NextStep: "Verify the engine, exact container name, and local permissions.", ExitCode: ExitEngineFailed}
		case RuntimeProtocol:
			return protocolFailure()
		case RuntimeRelease:
			return &CLIError{Class: string(runtimeError.Kind), Message: "The target release artifact could not be verified.", NextStep: "Use the matching release CLI and canonical container image in a prepared maintenance container.", ExitCode: ExitReleaseUnverified}
		}
	}
	return unexpectedError()
}

func interruptedError() *CLIError {
	return &CLIError{
		Class:    "interrupted",
		Message:  "The administration command was interrupted.",
		NextStep: "Inspect the operation state before retrying.",
		ExitCode: ExitInterrupted,
	}
}
