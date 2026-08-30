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
var idempotencyKeyPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`)
var applicationVersion = "development"
var applicationRevision = "unknown"
var applicationTag = ""

type buildMetadata struct {
	Identity string  `json:"identity"`
	Release  bool    `json:"release"`
	Revision string  `json:"revision"`
	Tag      *string `json:"tag"`
}

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
	if len(os.Args) == 2 && os.Args[1] == "--build-metadata" {
		_ = json.NewEncoder(os.Stdout).Encode(cliBuildMetadata())
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

func cliBuildMetadata() buildMetadata {
	metadata := buildMetadata{
		Identity: applicationVersion,
		Release:  applicationTag != "",
		Revision: applicationRevision,
	}
	if applicationTag != "" {
		tag := applicationTag
		metadata.Tag = &tag
	}
	return metadata
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
	memberID := commandSet.Int("member-id", 0, "committee member id")
	channel := commandSet.String("channel", "", "notification channel")
	idempotencyKey := commandSet.String("idempotency-key", "", "unique retry key")
	committeeID := commandSet.Int("committee-id", 0, "committee id")
	committeeName := commandSet.String("name", "", "committee name")
	committeeIHK := commandSet.String("ihk", "", "responsible IHK")
	committeeOccupation := commandSet.String("occupation", "", "training occupation")
	reason := commandSet.String("reason", "", "required lifecycle reason")
	chairExistingEmail := commandSet.String(
		"chair-existing-email", "", "existing chair person email",
	)
	chairFirstName := commandSet.String("chair-first-name", "", "new chair first name")
	chairLastName := commandSet.String("chair-last-name", "", "new chair last name")
	chairEmail := commandSet.String("chair-email", "", "new chair email")
	chairMobile := commandSet.String("chair-mobile", "", "new chair mobile number")
	chairMemberStatus := commandSet.String(
		"chair-member-status", "", "chair membership status",
	)
	chairRepresentingSide := commandSet.String(
		"chair-representing-side", "", "chair representing side",
	)
	deputyExistingEmail := commandSet.String(
		"deputy-existing-email", "", "existing deputy chair person email",
	)
	deputyFirstName := commandSet.String("deputy-first-name", "", "new deputy first name")
	deputyLastName := commandSet.String("deputy-last-name", "", "new deputy last name")
	deputyEmail := commandSet.String("deputy-email", "", "new deputy email")
	deputyMobile := commandSet.String("deputy-mobile", "", "new deputy mobile number")
	deputyMemberStatus := commandSet.String(
		"deputy-member-status", "", "deputy membership status",
	)
	deputyRepresentingSide := commandSet.String(
		"deputy-representing-side", "", "deputy representing side",
	)
	if err := commandSet.Parse(commandArgs); err != nil {
		return options{}, fmt.Errorf("invalid command option")
	}
	if commandSet.NArg() != 0 {
		return options{}, fmt.Errorf("unexpected command argument")
	}

	arguments := map[string]any{}
	committeeAdminFlagsUsed := strings.TrimSpace(*idempotencyKey) != "" ||
		*committeeID != 0 || strings.TrimSpace(*committeeName) != "" ||
		strings.TrimSpace(*committeeIHK) != "" || strings.TrimSpace(*committeeOccupation) != "" ||
		strings.TrimSpace(*reason) != "" || strings.TrimSpace(*chairExistingEmail) != "" ||
		strings.TrimSpace(*chairFirstName) != "" || strings.TrimSpace(*chairLastName) != "" ||
		strings.TrimSpace(*chairEmail) != "" || strings.TrimSpace(*chairMobile) != "" ||
		strings.TrimSpace(*chairMemberStatus) != "" || strings.TrimSpace(*chairRepresentingSide) != "" ||
		strings.TrimSpace(*deputyExistingEmail) != "" || strings.TrimSpace(*deputyFirstName) != "" ||
		strings.TrimSpace(*deputyLastName) != "" || strings.TrimSpace(*deputyEmail) != "" ||
		strings.TrimSpace(*deputyMobile) != "" || strings.TrimSpace(*deputyMemberStatus) != "" ||
		strings.TrimSpace(*deputyRepresentingSide) != ""
	switch command {
	case "bootstrap", "invite":
		if strings.TrimSpace(*email) == "" || *accountID != 0 || *memberID != 0 || *channel != "" || committeeAdminFlagsUsed {
			return options{}, fmt.Errorf("%s requires --email", command)
		}
		arguments["email"] = *email
	case "disable":
		if *accountID <= 0 || *email != "" || *memberID != 0 || *channel != "" || committeeAdminFlagsUsed {
			return options{}, fmt.Errorf("disable requires a positive --account-id")
		}
		arguments["account_id"] = *accountID
	case "recover":
		if (*accountID <= 0) == (strings.TrimSpace(*email) == "") || *memberID != 0 || *channel != "" || committeeAdminFlagsUsed {
			return options{}, fmt.Errorf("recover requires exactly one of --account-id or --email")
		}
		if *accountID > 0 {
			arguments["account_id"] = *accountID
		} else {
			arguments["email"] = *email
		}
	case "consume-invitation", "consume-recovery":
		if *email != "" || *accountID != 0 || *memberID != 0 || *channel != "" || committeeAdminFlagsUsed {
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
	case "process-notifications":
		if *email != "" || *accountID != 0 || *memberID != 0 || *channel != "" || committeeAdminFlagsUsed {
			return options{}, fmt.Errorf("process-notifications accepts no options")
		}
	case "test-notification":
		if *email != "" || *accountID != 0 || *memberID <= 0 || (*channel != "web_push" && *channel != "email") || committeeAdminFlagsUsed {
			return options{}, fmt.Errorf("test-notification requires --member-id and --channel web_push|email")
		}
		arguments["member_id"] = *memberID
		arguments["channel"] = *channel
	case "committee-bootstrap", "committee-complete":
		if !idempotencyKeyPattern.MatchString(*idempotencyKey) || *email != "" ||
			*accountID != 0 || *memberID != 0 || *channel != "" {
			return options{}, fmt.Errorf("%s requires a valid --idempotency-key", command)
		}
		chair, err := committeePersonSelection(
			"chair", true, *chairExistingEmail, *chairFirstName, *chairLastName,
			*chairEmail, *chairMobile, *chairMemberStatus, *chairRepresentingSide,
		)
		if err != nil {
			return options{}, err
		}
		deputy, err := committeePersonSelection(
			"deputy", false, *deputyExistingEmail, *deputyFirstName, *deputyLastName,
			*deputyEmail, *deputyMobile, *deputyMemberStatus, *deputyRepresentingSide,
		)
		if err != nil {
			return options{}, err
		}
		arguments["idempotency_key"] = *idempotencyKey
		arguments["chair"] = chair
		if deputy != nil {
			arguments["deputy"] = deputy
		}
		if command == "committee-bootstrap" {
			if strings.TrimSpace(*committeeName) == "" || strings.TrimSpace(*committeeIHK) == "" ||
				strings.TrimSpace(*committeeOccupation) == "" || *committeeID != 0 || strings.TrimSpace(*reason) != "" {
				return options{}, fmt.Errorf("committee-bootstrap requires --name, --ihk and --occupation")
			}
			arguments["committee"] = map[string]any{
				"name": *committeeName, "ihk": *committeeIHK, "occupation": *committeeOccupation,
			}
		} else {
			if *committeeID <= 0 || strings.TrimSpace(*committeeName) != "" ||
				strings.TrimSpace(*committeeIHK) != "" || strings.TrimSpace(*committeeOccupation) != "" || strings.TrimSpace(*reason) != "" {
				return options{}, fmt.Errorf("committee-complete requires a positive --committee-id")
			}
			arguments["committee_id"] = *committeeID
		}
	case "committee-reinvite":
		if !idempotencyKeyPattern.MatchString(*idempotencyKey) || *committeeID <= 0 ||
			strings.TrimSpace(*email) == "" || *accountID != 0 || *memberID != 0 || *channel != "" ||
			committeePersonFlagsUsed(*chairExistingEmail, *chairFirstName, *chairLastName, *chairEmail, *chairMobile, *chairMemberStatus, *chairRepresentingSide) ||
			committeePersonFlagsUsed(*deputyExistingEmail, *deputyFirstName, *deputyLastName, *deputyEmail, *deputyMobile, *deputyMemberStatus, *deputyRepresentingSide) ||
			strings.TrimSpace(*committeeName) != "" || strings.TrimSpace(*committeeIHK) != "" ||
			strings.TrimSpace(*committeeOccupation) != "" || strings.TrimSpace(*reason) != "" {
			return options{}, fmt.Errorf("committee-reinvite requires --idempotency-key, --committee-id and --email")
		}
		arguments["idempotency_key"] = *idempotencyKey
		arguments["committee_id"] = *committeeID
		arguments["email"] = *email
	case "committee-deactivate", "committee-reactivate":
		if !idempotencyKeyPattern.MatchString(*idempotencyKey) || *committeeID <= 0 ||
			strings.TrimSpace(*reason) == "" || *email != "" || *accountID != 0 ||
			*memberID != 0 || *channel != "" || strings.TrimSpace(*committeeName) != "" ||
			strings.TrimSpace(*committeeIHK) != "" || strings.TrimSpace(*committeeOccupation) != "" ||
			committeePersonFlagsUsed(*chairExistingEmail, *chairFirstName, *chairLastName, *chairEmail, *chairMobile, *chairMemberStatus, *chairRepresentingSide) ||
			committeePersonFlagsUsed(*deputyExistingEmail, *deputyFirstName, *deputyLastName, *deputyEmail, *deputyMobile, *deputyMemberStatus, *deputyRepresentingSide) {
			return options{}, fmt.Errorf("%s requires --idempotency-key, --committee-id and --reason", command)
		}
		arguments["idempotency_key"] = *idempotencyKey
		arguments["committee_id"] = *committeeID
		arguments["reason"] = *reason
	default:
		return options{}, fmt.Errorf("unsupported admin command")
	}

	return options{engine: *engine, container: *container, command: command, arguments: arguments}, nil
}

func committeePersonFlagsUsed(values ...string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return true
		}
	}
	return false
}

func committeePersonSelection(
	prefix string,
	required bool,
	existingEmail string,
	firstName string,
	lastName string,
	email string,
	mobile string,
	memberStatus string,
	representingSide string,
) (map[string]any, error) {
	existing := strings.TrimSpace(existingEmail) != ""
	newPerson := committeePersonFlagsUsed(firstName, lastName, email, mobile)
	membership := committeePersonFlagsUsed(memberStatus, representingSide)
	if !existing && !newPerson && !membership {
		if required {
			return nil, fmt.Errorf("%s person selection is required", prefix)
		}
		return nil, nil
	}
	if existing == newPerson || !membership {
		return nil, fmt.Errorf(
			"%s requires exactly one existing or new person path and membership fields",
			prefix,
		)
	}
	if memberStatus != "ordinary" && memberStatus != "deputy" {
		return nil, fmt.Errorf("%s member status must be ordinary or deputy", prefix)
	}
	if representingSide != "employer" && representingSide != "employee" && representingSide != "school" {
		return nil, fmt.Errorf("%s representing side is invalid", prefix)
	}
	selection := map[string]any{
		"member_status":     memberStatus,
		"representing_side": representingSide,
	}
	if existing {
		selection["mode"] = "existing"
		selection["email"] = existingEmail
		return selection, nil
	}
	if strings.TrimSpace(firstName) == "" || strings.TrimSpace(lastName) == "" || strings.TrimSpace(email) == "" {
		return nil, fmt.Errorf("%s new person requires first name, last name and email", prefix)
	}
	selection["mode"] = "new"
	selection["first_name"] = firstName
	selection["last_name"] = lastName
	selection["email"] = email
	if strings.TrimSpace(mobile) != "" {
		selection["mobile"] = mobile
	}
	return selection, nil
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
