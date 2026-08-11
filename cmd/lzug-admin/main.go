package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"
)

const (
	protocolVersion       = 1
	exitEngineUnavailable = 10
	exitEngineFailed      = 11
	maxTokenInput         = 512
)

var containerNamePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`)
var applicationVersion = "development"

type request struct {
	Version   int            `json:"version"`
	Command   string         `json:"command"`
	Arguments map[string]any `json:"arguments"`
}

type options struct {
	engine    string
	container string
	command   string
	arguments map[string]any
}

type runner struct {
	engine    string
	container string
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		_, _ = fmt.Fprintln(os.Stdout, versionText())
		return
	}
	opts, err := parseOptions(os.Args[1:], os.Stdin)
	if err != nil {
		writeLocalError(os.Stdout, "invalid_request", err.Error())
		os.Exit(2)
	}
	payload, err := json.Marshal(request{
		Version:   protocolVersion,
		Command:   opts.command,
		Arguments: opts.arguments,
	})
	if err != nil {
		writeLocalError(os.Stdout, "invalid_request", "Request could not be encoded")
		os.Exit(2)
	}
	payload = append(payload, '\n')

	code, err := (runner{engine: opts.engine, container: opts.container}).execute(
		context.Background(), payload, os.Stdout, os.Stderr,
	)
	if err != nil {
		class := "engine_invocation_failed"
		code = exitEngineFailed
		if errors.Is(err, exec.ErrNotFound) {
			class = "engine_unavailable"
			code = exitEngineUnavailable
		}
		writeLocalError(os.Stdout, class, "Container engine could not be invoked")
	}
	os.Exit(code)
}

func versionText() string {
	return "lzug-admin " + applicationVersion
}

func parseOptions(args []string, input io.Reader) (options, error) {
	global := flag.NewFlagSet("lzug-admin", flag.ContinueOnError)
	global.SetOutput(io.Discard)
	engine := global.String("engine", "", "Docker or Podman")
	container := global.String("container", "", "exact running container name")
	if err := global.Parse(args); err != nil {
		return options{}, fmt.Errorf("invalid global option")
	}
	if !containerNamePattern.MatchString(*container) {
		return options{}, fmt.Errorf("container must be a valid exact container name")
	}
	if *engine != "" && *engine != "docker" && *engine != "podman" {
		return options{}, fmt.Errorf("engine must be docker or podman")
	}
	remaining := global.Args()
	if len(remaining) == 0 {
		return options{}, fmt.Errorf("an admin command is required")
	}

	command := remaining[0]
	commandArgs := remaining[1:]
	commandSet := flag.NewFlagSet(command, flag.ContinueOnError)
	commandSet.SetOutput(io.Discard)
	email := commandSet.String("email", "", "account email")
	accountID := commandSet.Int("account-id", 0, "account id")
	if err := commandSet.Parse(commandArgs); err != nil {
		return options{}, fmt.Errorf("invalid command option")
	}
	if commandSet.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected command argument")
	}

	arguments := map[string]any{}
	switch command {
	case "bootstrap", "invite":
		if strings.TrimSpace(*email) == "" || *accountID != 0 {
			return options{}, fmt.Errorf("%s requires --email", command)
		}
		arguments["email"] = *email
	case "disable":
		if *accountID <= 0 || *email != "" {
			return options{}, fmt.Errorf("disable requires a positive --account-id")
		}
		arguments["account_id"] = *accountID
	case "recover":
		if (*accountID <= 0) == (strings.TrimSpace(*email) == "") {
			return options{}, fmt.Errorf("recover requires exactly one of --account-id or --email")
		}
		if *accountID > 0 {
			arguments["account_id"] = *accountID
		} else {
			arguments["email"] = *email
		}
	case "consume-invitation", "consume-recovery":
		if *email != "" || *accountID != 0 {
			return options{}, fmt.Errorf("%s reads its token from stdin", command)
		}
		token, err := io.ReadAll(io.LimitReader(input, maxTokenInput+1))
		if err != nil || len(token) > maxTokenInput {
			return options{}, fmt.Errorf("token input is too large")
		}
		secret := strings.TrimSpace(string(token))
		if secret == "" || strings.ContainsAny(secret, "\r\n") {
			return options{}, fmt.Errorf("token input is required")
		}
		arguments["token"] = secret
	default:
		return options{}, fmt.Errorf("unsupported admin command")
	}

	return options{engine: *engine, container: *container, command: command, arguments: arguments}, nil
}

func (r runner) execute(ctx context.Context, input []byte, stdout, stderr io.Writer) (int, error) {
	engine, err := resolveEngine(r.engine)
	if err != nil {
		return exitEngineUnavailable, err
	}
	if !containerNamePattern.MatchString(r.container) {
		return exitEngineFailed, fmt.Errorf("invalid container")
	}
	command := exec.CommandContext(
		ctx,
		engine,
		"exec",
		"--interactive",
		r.container,
		"python",
		"-m",
		"backend.admin",
		"--protocol",
		fmt.Sprint(protocolVersion),
	)
	command.Stdin = strings.NewReader(string(input))
	command.Stdout = stdout
	command.Stderr = stderr
	if err := command.Run(); err != nil {
		var exitError *exec.ExitError
		if errors.As(err, &exitError) {
			return exitError.ExitCode(), nil
		}
		return exitEngineFailed, err
	}
	return 0, nil
}

func resolveEngine(preferred string) (string, error) {
	if preferred != "" {
		return exec.LookPath(preferred)
	}
	for _, candidate := range []string{"docker", "podman"} {
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	return "", exec.ErrNotFound
}

func writeLocalError(output io.Writer, class, message string) {
	payload := map[string]any{
		"version": protocolVersion,
		"ok":      false,
		"error": map[string]string{
			"class":   class,
			"message": message,
		},
	}
	encoded, _ := json.Marshal(payload)
	_, _ = fmt.Fprintf(output, "%s\n", encoded)
}
