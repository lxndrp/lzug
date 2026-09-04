package admincli

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"
)

var commandTokenPattern = regexp.MustCompile(`^[a-z][a-z0-9-]*$`)

type CommandGroup struct {
	Name        string
	Summary     string
	Description string
}

type Registry struct {
	commands []*Command
	byName   map[string]*Command
	groups   map[string]CommandGroup
}

func DefaultRegistry() (*Registry, error) {
	groups := []CommandGroup{
		{Name: "account", Summary: "Manage operator accounts and one-time credentials.", Description: "Bootstrap, invite, disable, recover, or consume one-time account credentials."},
		{Name: "artifact", Summary: "Inspect protected artifact metadata.", Description: "Inspect only the public minimum preamble without decrypting business data."},
		{Name: "backup", Summary: "Create, verify, and restore protected backups.", Description: "Operate protected backup artifacts through the versioned local administration boundary."},
		{Name: "committee", Summary: "Bootstrap and maintain examination committees.", Description: "Perform idempotent committee bootstrap and lifecycle administration."},
		{Name: "completion", Summary: "Generate shell completion scripts.", Description: "Print an installable completion script without changing shell configuration."},
		{Name: "config", Summary: "Inspect local CLI configuration.", Description: "Inspect effective non-secret CLI settings and their source."},
		{Name: "export", Summary: "Create and verify protected full exports.", Description: "Operate protected full-export artifacts through the versioned local administration boundary."},
		{Name: "notification", Summary: "Process and test technical notifications.", Description: "Run secret-free notification processing and synthetic delivery diagnostics."},
		{Name: "plan-consequence", Summary: "Inspect and retry confirmed-plan consequences.", Description: "Inspect or retry technical follow-up work without exposing business content."},
		{Name: "recipient-key", Summary: "Manage local age recipient keys.", Description: "Generate and inspect local X25519 age identities without transmitting private keys."},
		{Name: "system", Summary: "Inspect the local runtime and its readiness.", Description: "Run secret-free configuration, status, and diagnostic checks in the selected container."},
		{Name: "upgrade", Summary: "Apply upgrades and inspect rollback eligibility.", Description: "Use release-bound lifecycle operations in a prepared maintenance container."},
	}
	commands := make([]Command, 0, 32)
	commands = append(commands, accountCommands()...)
	commands = append(commands, committeeCommands()...)
	commands = append(commands, systemCommands()...)
	commands = append(commands, artifactCommands()...)
	commands = append(commands, operationalCommands()...)
	commands = append(commands, localCommands()...)
	return NewRegistry(groups, commands)
}

func NewRegistry(groups []CommandGroup, commands []Command) (*Registry, error) {
	registry := &Registry{
		commands: make([]*Command, 0, len(commands)),
		byName:   make(map[string]*Command, len(commands)),
		groups:   make(map[string]CommandGroup, len(groups)),
	}
	for _, group := range groups {
		if !commandTokenPattern.MatchString(group.Name) || strings.TrimSpace(group.Summary) == "" || strings.TrimSpace(group.Description) == "" {
			return nil, fmt.Errorf("invalid command group metadata for %q", group.Name)
		}
		if _, exists := registry.groups[group.Name]; exists {
			return nil, fmt.Errorf("duplicate command group %q", group.Name)
		}
		registry.groups[group.Name] = group
	}
	legacy := map[string]string{}
	for index := range commands {
		command := commands[index]
		applyInteractiveMetadata(&command)
		if (command.BackendCommand != "" || command.UsesConfig) && command.Timeout == 0 {
			command.Timeout = commandTimeout(command.Name())
		}
		if err := validateCommand(command, registry.groups); err != nil {
			return nil, err
		}
		name := command.Name()
		if _, exists := registry.byName[name]; exists {
			return nil, fmt.Errorf("duplicate command %q", name)
		}
		for _, old := range command.LegacyForms {
			if previous, exists := legacy[old]; exists {
				return nil, fmt.Errorf("legacy form %q is assigned to both %q and %q", old, previous, name)
			}
			legacy[old] = name
		}
		stored := command
		registry.commands = append(registry.commands, &stored)
		registry.byName[name] = &stored
	}
	sort.Slice(registry.commands, func(left, right int) bool {
		return registry.commands[left].Name() < registry.commands[right].Name()
	})
	return registry, nil
}

func commandTimeout(name string) time.Duration {
	switch name {
	case "backup restore", "upgrade apply":
		return 30 * time.Minute
	case "backup create", "export create", "notification process", "plan-consequence retry":
		return 10 * time.Minute
	default:
		return 2 * time.Minute
	}
}

func applyInteractiveMetadata(command *Command) {
	terms := map[string][]string{
		"account":          {"konto", "benutzer", "einladung", "wiederherstellung"},
		"backup":           {"sicherung", "wiederherstellung", "restore"},
		"cli":              {"dialog", "interaktiv", "geführt"},
		"committee":        {"ausschuss", "prüfungsausschuss", "mitglied"},
		"completion":       {"shell", "vervollstaendigung"},
		"config":           {"konfiguration", "ziel", "engine", "container"},
		"export":           {"export", "archiv"},
		"notification":     {"benachrichtigung", "zustellung"},
		"plan-consequence": {"planfolge", "termin", "status"},
		"system":           {"system", "diagnose", "bereitschaft", "status"},
		"upgrade":          {"aktualisierung", "migration", "rollback"},
	}
	command.SearchTerms = append(command.SearchTerms, terms[command.Path[0]]...)
	readOnly := map[string]bool{
		"artifact inspect":        true,
		"backup verify":           true,
		"backup recipient show":   true,
		"config inspect":          true,
		"export verify":           true,
		"plan-consequence status": true,
		"system config":           true,
		"system doctor":           true,
		"system status":           true,
		"upgrade rollback":        true,
	}
	localMutations := map[string]bool{
		"backup create":            true,
		"backup recipient replace": true,
		"backup recipient set":     true,
		"backup restore":           true,
		"export create":            true,
	}
	command.Mutating = (command.BackendCommand != "" && !readOnly[command.Name()]) || localMutations[command.Name()]
	command.RetrySafe = readOnly[command.Name()] || strings.HasPrefix(command.Name(), "completion ") || strings.HasPrefix(command.Name(), "committee ")
}

func validateCommand(command Command, groups map[string]CommandGroup) error {
	if len(command.Path) == 0 || len(command.Path) > 3 {
		return fmt.Errorf("command path must contain one to three tokens")
	}
	for _, token := range command.Path {
		if !commandTokenPattern.MatchString(token) {
			return fmt.Errorf("invalid command token %q", token)
		}
	}
	if len(command.Path) >= 2 {
		if _, exists := groups[command.Path[0]]; !exists {
			return fmt.Errorf("command %q references an unknown group", command.Name())
		}
	}
	if strings.TrimSpace(command.Summary) == "" || strings.TrimSpace(command.Description) == "" || len(command.Examples) == 0 {
		return fmt.Errorf("command %q has incomplete help metadata", command.Name())
	}
	if command.Output.Human == "" || strings.TrimSpace(command.Output.Summary) == "" {
		return fmt.Errorf("command %q has incomplete output metadata", command.Name())
	}
	if command.Output.Verbose != VerboseSummary || (command.Output.JSON != JSONProjected && command.Output.JSON != JSONLocal) {
		return fmt.Errorf("command %q has incomplete verbose or JSON metadata", command.Name())
	}
	if (command.BackendCommand == "") == (command.Local == nil) {
		return fmt.Errorf("command %q must declare exactly one backend or local handler", command.Name())
	}
	if command.BackendCommand != "" && command.Transport != ContainerExecTransport || command.Local != nil && command.Transport != LocalTransport {
		return fmt.Errorf("command %q has an invalid transport declaration", command.Name())
	}
	if command.BackendCommand != "" && command.Output.JSON != JSONProjected || command.Local != nil && command.Output.JSON != JSONLocal {
		return fmt.Errorf("command %q has an invalid JSON output declaration", command.Name())
	}
	if command.BackendCommand != "" && command.BuildRequest == nil {
		return fmt.Errorf("command %q has no request builder", command.Name())
	}
	if command.BackendCommand != "" && len(command.Output.ResultKeys) == 0 {
		return fmt.Errorf("command %q has no allowed JSON result fields", command.Name())
	}
	if command.Confirmation.Required && command.Confirmation.Prompt == nil {
		return fmt.Errorf("command %q has no confirmation prompt", command.Name())
	}
	argumentNames := map[string]struct{}{}
	optionalArgumentSeen := false
	for _, argument := range command.Arguments {
		if !commandTokenPattern.MatchString(argument.Name) || strings.TrimSpace(argument.Summary) == "" {
			return fmt.Errorf("command %q has invalid argument metadata for %q", command.Name(), argument.Name)
		}
		if optionalArgumentSeen && argument.Required {
			return fmt.Errorf("command %q places required argument %q after an optional argument", command.Name(), argument.Name)
		}
		optionalArgumentSeen = optionalArgumentSeen || !argument.Required
		if _, exists := argumentNames[argument.Name]; exists {
			return fmt.Errorf("command %q has duplicate argument %q", command.Name(), argument.Name)
		}
		argumentNames[argument.Name] = struct{}{}
	}
	optionNames := map[string]struct{}{}
	for _, option := range command.Options {
		if !commandTokenPattern.MatchString(option.Name) || strings.TrimSpace(option.Summary) == "" {
			return fmt.Errorf("command %q has invalid option metadata for %q", command.Name(), option.Name)
		}
		if option.Kind != StringOption && option.Kind != IntegerOption && option.Kind != BooleanOption {
			return fmt.Errorf("command %q has invalid option kind for %q", command.Name(), option.Name)
		}
		if option.Kind != BooleanOption && strings.TrimSpace(option.ValueName) == "" {
			return fmt.Errorf("command %q has no value name for %q", command.Name(), option.Name)
		}
		if option.DangerZone && option.Kind != BooleanOption {
			return fmt.Errorf("command %q has a non-boolean danger-zone option %q", command.Name(), option.Name)
		}
		if _, exists := optionNames[option.Name]; exists {
			return fmt.Errorf("command %q has duplicate option %q", command.Name(), option.Name)
		}
		if _, exists := argumentNames[option.Name]; exists {
			return fmt.Errorf("command %q reuses argument %q as an option", command.Name(), option.Name)
		}
		optionNames[option.Name] = struct{}{}
	}
	secretNames := map[string]struct{}{}
	for _, secret := range command.Secrets {
		if !commandTokenPattern.MatchString(secret.Name) || strings.TrimSpace(secret.Description) == "" || strings.TrimSpace(secret.Prompt) == "" || secret.Input != SecretStdin {
			return fmt.Errorf("command %q has invalid secret metadata", command.Name())
		}
		if _, exposed := optionNames[secret.Name]; exposed {
			return fmt.Errorf("command %q exposes secret %q as an option", command.Name(), secret.Name)
		}
		if _, exists := secretNames[secret.Name]; exists {
			return fmt.Errorf("command %q has duplicate secret %q", command.Name(), secret.Name)
		}
		secretNames[secret.Name] = struct{}{}
	}
	resultKeys := map[string]struct{}{}
	for _, key := range command.Output.ResultKeys {
		if !commandTokenPattern.MatchString(strings.ReplaceAll(key, "_", "-")) {
			return fmt.Errorf("command %q has invalid JSON result field %q", command.Name(), key)
		}
		if _, exists := resultKeys[key]; exists {
			return fmt.Errorf("command %q has duplicate JSON result field %q", command.Name(), key)
		}
		resultKeys[key] = struct{}{}
	}
	for _, old := range command.LegacyForms {
		if strings.TrimSpace(old) == "" {
			return fmt.Errorf("command %q has an empty legacy mapping", command.Name())
		}
	}
	return nil
}

func (r *Registry) Commands() []*Command {
	commands := make([]*Command, len(r.commands))
	copy(commands, r.commands)
	return commands
}

func (r *Registry) Find(path []string) (*Command, bool) {
	command, exists := r.byName[strings.Join(path, " ")]
	return command, exists
}

func (r *Registry) Group(name string) (CommandGroup, bool) {
	group, exists := r.groups[name]
	return group, exists
}

func (r *Registry) Groups() []CommandGroup {
	groups := make([]CommandGroup, 0, len(r.groups))
	for _, group := range r.groups {
		groups = append(groups, group)
	}
	sort.Slice(groups, func(left, right int) bool { return groups[left].Name < groups[right].Name })
	return groups
}

func (r *Registry) CommandsInGroup(name string) []*Command {
	commands := []*Command{}
	for _, command := range r.commands {
		if len(command.Path) >= 2 && command.Path[0] == name {
			commands = append(commands, command)
		}
	}
	return commands
}
