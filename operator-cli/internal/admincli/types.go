package admincli

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"
)

const (
	ProtocolVersion = 1
	SchemaVersion   = 1

	ExitOK                   = 0
	ExitUnexpected           = 1
	ExitInvalidInvocation    = 2
	ExitEngineUnavailable    = 10
	ExitEngineFailed         = 11
	ExitConfiguration        = 12
	ExitReleaseUnverified    = 33
	ExitProtocolIncompatible = 40
	ExitInterrupted          = 130
)

type BuildInfo struct {
	Version  string
	Revision string
	Tag      string
}

type BackendRequest struct {
	Version   int            `json:"version"`
	Command   string         `json:"command"`
	Arguments map[string]any `json:"arguments"`
}

type BackendError struct {
	Class   string          `json:"class"`
	Message string          `json:"message"`
	Phase   string          `json:"phase,omitempty"`
	Details json.RawMessage `json:"details,omitempty"`
}

type BackendResponse struct {
	Version int             `json:"version"`
	OK      bool            `json:"ok"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *BackendError   `json:"error,omitempty"`
}

type Transport interface {
	Execute(context.Context, BackendRequest) (BackendResponse, int, error)
}

type ReleaseInspector interface {
	Target(context.Context, BuildInfo) (map[string]any, error)
}

type RuntimeFactory interface {
	Transport(EffectiveConfig) Transport
	ReleaseInspector(EffectiveConfig) ReleaseInspector
}

type ArtifactTransport interface {
	Produce(context.Context, BackendRequest, io.Writer) (BackendResponse, int, error)
	Consume(context.Context, BackendRequest, io.Reader) (BackendResponse, int, error)
}

type ArtifactRuntimeFactory interface {
	ArtifactTransport(EffectiveConfig) ArtifactTransport
}

type ConfigResolver interface {
	Resolve(GlobalOptions) (EffectiveConfig, *CLIError)
}

type Input interface {
	IsTerminal() bool
	Confirm(string) (bool, error)
	ReadSecret(string) (string, error)
}

// InteractiveInput extends secure command input with line-oriented dialog
// input. Implementations must never route secret values through ReadLine.
type InteractiveInput interface {
	Input
	ReadLine(context.Context, string) (string, error)
}

type Renderer interface {
	Error(GlobalOptions, string, *CLIError)
	Informational(GlobalOptions, any, string) *CLIError
	Progress(GlobalOptions, *Command, string, int)
	LocalSuccess(GlobalOptions, *Command, LocalResult) *CLIError
	Backend(GlobalOptions, *Command, BackendResponse, int) *CLIError
}

// InteractiveRenderer is the terminal boundary used by the guided session.
// Dialog output is plain, linear text and never requires ANSI support.
type InteractiveRenderer interface {
	Renderer
	IsTerminal() bool
	Dialog(string) error
}

type TransportKind string

const (
	ContainerExecTransport TransportKind = "container-exec"
	LocalTransport         TransportKind = "local"
)

type OptionKind string

const (
	StringOption  OptionKind = "string"
	IntegerOption OptionKind = "integer"
	BooleanOption OptionKind = "boolean"
)

type OptionSpec struct {
	Name        string
	ValueName   string
	Summary     string
	Kind        OptionKind
	Required    bool
	Positive    bool
	Choices     []string
	DangerZone  bool
	DefaultText string
}

type ArgumentSpec struct {
	Name     string
	Summary  string
	Required bool
	Choices  []string
}

type SecretInput string

const SecretStdin SecretInput = "stdin"

type SecretSpec struct {
	Name        string
	Description string
	Prompt      string
	Input       SecretInput
}

type ConfirmationSpec struct {
	Required bool
	Deferred bool
	Prompt   func(Values, EffectiveConfig) string
}

type HumanOutput string

const (
	HumanSilent      HumanOutput = "silent"
	HumanToken       HumanOutput = "token"
	HumanInvitations HumanOutput = "invitations"
	HumanArtifact    HumanOutput = "artifact"
	HumanDiagnostics HumanOutput = "diagnostics"
	HumanPlanStatus  HumanOutput = "plan-status"
	HumanLocal       HumanOutput = "local"
)

type VerboseOutput string

const VerboseSummary VerboseOutput = "summary"

type JSONOutput string

const (
	JSONProjected JSONOutput = "projected"
	JSONLocal     JSONOutput = "local"
)

type OutputSpec struct {
	Human      HumanOutput
	Verbose    VerboseOutput
	JSON       JSONOutput
	Summary    string
	ResultKeys []string
}

type Values map[string]any

func (v Values) String(name string) string {
	value, _ := v[name].(string)
	return value
}

func (v Values) Int(name string) int {
	value, _ := v[name].(int)
	return value
}

func (v Values) Bool(name string) bool {
	value, _ := v[name].(bool)
	return value
}

type PrepareContext struct {
	Build            BuildInfo
	ReleaseInspector ReleaseInspector
}

type LocalContext struct {
	Registry *Registry
	Config   EffectiveConfig
	Runtime  RuntimeFactory
	Input    Input
	Global   GlobalOptions
	Build    BuildInfo
}

type LocalResult struct {
	Result      any
	HumanOutput string
}

type Command struct {
	Path           []string
	Summary        string
	Description    string
	Examples       []string
	Arguments      []ArgumentSpec
	Options        []OptionSpec
	Secrets        []SecretSpec
	Confirmation   ConfirmationSpec
	UsesConfig     bool
	Transport      TransportKind
	BackendCommand string
	LegacyForms    []string
	Output         OutputSpec
	SearchTerms    []string
	Mutating       bool
	RetrySafe      bool
	Timeout        time.Duration
	Validate       func(Values) error
	BuildRequest   func(context.Context, PrepareContext, Values, Values) (BackendRequest, error)
	Local          func(context.Context, LocalContext, Values) (LocalResult, *CLIError)
}

func (c Command) Name() string {
	return strings.Join(c.Path, " ")
}

func (c Command) IsLocal() bool {
	return c.Transport == LocalTransport
}

type GlobalOptions struct {
	Engine       string
	EngineSet    bool
	Container    string
	ContainerSet bool
	ConfigPath   string
	ConfigSet    bool
	NoConfig     bool
	JSON         bool
	Verbose      bool
	Force        bool
	ForceSet     bool
}

type EffectiveValue struct {
	Value  string `json:"value"`
	Source string `json:"source"`
}

type EffectiveConfig struct {
	Engine    EffectiveValue `json:"engine"`
	Container EffectiveValue `json:"container"`
}

type CLIError struct {
	Class    string
	Message  string
	NextStep string
	ExitCode int
	Phase    string
	Details  map[string]any
}

func (e *CLIError) Error() string {
	return e.Message
}

func invalidInvocation(format string, arguments ...any) *CLIError {
	return &CLIError{
		Class:    "invalid_invocation",
		Message:  fmt.Sprintf(format, arguments...),
		NextStep: "Run lzug-admin --help or the contextual --help command.",
		ExitCode: ExitInvalidInvocation,
	}
}

func unexpectedError() *CLIError {
	return &CLIError{
		Class:    "unexpected_local_error",
		Message:  "The local administration command failed unexpectedly.",
		NextStep: "Retry with --verbose and verify the local installation.",
		ExitCode: ExitUnexpected,
	}
}

type Application struct {
	Registry *Registry
	Build    BuildInfo
	Runtime  RuntimeFactory
	Config   ConfigResolver
	Input    Input
	Renderer Renderer
}
