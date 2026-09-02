package admincli

import (
	"reflect"
	"sort"
	"testing"
)

func TestDefaultRegistryContainsTheCompletePublicCommandTree(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	got := []string{}
	for _, command := range registry.Commands() {
		got = append(got, command.Name())
	}
	want := []string{
		"account bootstrap", "account consume-invitation", "account consume-recovery",
		"account disable", "account invite", "account recover",
		"backup create", "backup restore", "backup verify", "cli",
		"committee bootstrap", "committee complete", "committee deactivate",
		"committee reactivate", "committee reinvite",
		"completion bash", "completion fish", "completion powershell", "completion zsh",
		"config inspect", "export create", "export verify",
		"notification process", "notification test",
		"plan-consequence retry", "plan-consequence status",
		"system config", "system doctor", "system status",
		"upgrade apply", "upgrade rollback",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("unexpected command tree:\n got: %#v\nwant: %#v", got, want)
	}
}

func TestEveryLegacyFormHasExactlyOneMigrationTarget(t *testing.T) {
	registry, err := DefaultRegistry()
	if err != nil {
		t.Fatal(err)
	}
	got := []string{}
	for _, command := range registry.Commands() {
		got = append(got, command.LegacyForms...)
	}
	sort.Strings(got)
	want := []string{
		"artifact-verify (backup artifact)", "artifact-verify (full-export artifact)",
		"backup-create", "backup-restore", "bootstrap", "committee-bootstrap",
		"committee-complete", "committee-deactivate", "committee-reactivate",
		"committee-reinvite", "config", "consume-invitation", "consume-recovery",
		"disable", "doctor", "full-export", "invite", "plan-consequences-status",
		"process-notifications", "recover", "retry-plan-consequences", "rollback",
		"status", "test-notification", "upgrade",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("unexpected legacy mapping:\n got: %#v\nwant: %#v", got, want)
	}
}

func TestRegistryRejectsDuplicatesAndIncompleteMetadata(t *testing.T) {
	groups := []CommandGroup{{Name: "test", Summary: "Test commands.", Description: "Test command group."}}
	valid := Command{
		Path:           []string{"test", "run"},
		Summary:        "Run a test.",
		Description:    "Run a deterministic test command.",
		Examples:       []string{"lzug-admin test run"},
		Transport:      ContainerExecTransport,
		BackendCommand: "test",
		Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent.", ResultKeys: []string{"status"}},
		BuildRequest:   simpleRequest("test", func(_, _ Values) map[string]any { return map[string]any{} }),
	}
	if _, err := NewRegistry(groups, []Command{valid, valid}); err == nil {
		t.Fatal("duplicate command was accepted")
	}
	invalid := valid
	invalid.Summary = ""
	if _, err := NewRegistry(groups, []Command{invalid}); err == nil {
		t.Fatal("incomplete command metadata was accepted")
	}
	secretOption := valid
	secretOption.Options = []OptionSpec{{Name: "token", ValueName: "TOKEN", Summary: "A token.", Kind: StringOption}}
	secretOption.Secrets = []SecretSpec{{Name: "token", Description: "Secret token.", Prompt: "Token"}}
	if _, err := NewRegistry(groups, []Command{secretOption}); err == nil {
		t.Fatal("secret argv option was accepted")
	}
	invalidArguments := valid
	invalidArguments.Arguments = []ArgumentSpec{
		{Name: "optional", Summary: "Optional value."},
		{Name: "required", Summary: "Required value.", Required: true},
	}
	if _, err := NewRegistry(groups, []Command{invalidArguments}); err == nil {
		t.Fatal("required argument after optional argument was accepted")
	}
}

func TestStructuredArgumentSchemaParsesDeclaredStaticValues(t *testing.T) {
	command := &Command{
		Path:      []string{"test"},
		Arguments: []ArgumentSpec{{Name: "mode", Summary: "Execution mode.", Required: true, Choices: []string{"check", "apply"}}},
	}
	values, failure := parseCommandOptions(command, []string{"check"})
	if failure != nil || values.String("mode") != "check" {
		t.Fatalf("declared argument was not parsed: values=%#v failure=%v", values, failure)
	}
	if _, failure := parseCommandOptions(command, []string{"unknown"}); failure == nil {
		t.Fatal("undeclared argument choice was accepted")
	}
}
