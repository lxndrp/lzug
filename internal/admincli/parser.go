package admincli

import (
	"fmt"
	"strconv"
	"strings"
)

type invocation struct {
	command *Command
	args    []string
}

func parseGlobalOptions(args []string) (GlobalOptions, []string, *CLIError) {
	options := GlobalOptions{JSON: jsonOutputRequested(args)}
	remaining := make([]string, 0, len(args))
	seen := map[string]bool{}
	for index := 0; index < len(args); index++ {
		token := args[index]
		if token == "--" {
			remaining = append(remaining, args[index:]...)
			break
		}
		name, inline, hasInline := splitLongOption(token)
		switch name {
		case "engine", "container", "config":
			if seen[name] {
				return options, nil, invalidInvocation("--%s may be specified only once", name)
			}
			value := inline
			if !hasInline {
				index++
				if index >= len(args) || strings.HasPrefix(args[index], "--") {
					return options, nil, invalidInvocation("--%s requires a value", name)
				}
				value = args[index]
			}
			if strings.TrimSpace(value) == "" {
				return options, nil, invalidInvocation("--%s requires a non-empty value", name)
			}
			seen[name] = true
			switch name {
			case "engine":
				options.Engine, options.EngineSet = value, true
			case "container":
				options.Container, options.ContainerSet = value, true
			case "config":
				options.ConfigPath, options.ConfigSet = value, true
			}
		case "no-config", "json", "verbose", "force":
			if seen[name] {
				return options, nil, invalidInvocation("--%s may be specified only once", name)
			}
			value := true
			if hasInline {
				parsed, err := strconv.ParseBool(inline)
				if err != nil {
					return options, nil, invalidInvocation("--%s requires true or false", name)
				}
				value = parsed
			}
			seen[name] = true
			switch name {
			case "no-config":
				options.NoConfig = value
			case "json":
				options.JSON = options.JSON || value
			case "verbose":
				options.Verbose = value
			case "force":
				options.Force, options.ForceSet = value, true
			}
		default:
			remaining = append(remaining, token)
		}
	}
	if options.ConfigSet && options.NoConfig {
		return options, nil, invalidInvocation("--config and --no-config cannot be combined")
	}
	return options, remaining, nil
}

func jsonOutputRequested(args []string) bool {
	for _, token := range args {
		name, inline, hasInline := splitLongOption(token)
		if name != "json" {
			continue
		}
		if !hasInline {
			return true
		}
		value, err := strconv.ParseBool(inline)
		if err != nil || value {
			return true
		}
	}
	return false
}

func splitLongOption(token string) (name string, value string, hasValue bool) {
	if !strings.HasPrefix(token, "--") {
		return "", "", false
	}
	name = strings.TrimPrefix(token, "--")
	if before, after, found := strings.Cut(name, "="); found {
		return before, after, true
	}
	return name, "", false
}

func resolveInvocation(registry *Registry, args []string) (invocation, string, *CLIError) {
	if len(args) == 0 {
		return invocation{}, "root", invalidInvocation("an admin command is required")
	}
	if args[0] == "--help" || args[0] == "-h" {
		if len(args) != 1 {
			return invocation{}, "root", invalidInvocation("--help accepts no arguments")
		}
		return invocation{}, "root", nil
	}
	root := args[0]
	if _, isGroup := registry.Group(root); isGroup {
		if len(args) == 1 {
			return invocation{}, root, invalidInvocation("%s requires an action", root)
		}
		if args[1] == "--help" || args[1] == "-h" {
			if len(args) != 2 {
				return invocation{}, root, invalidInvocation("--help accepts no arguments")
			}
			return invocation{}, root, nil
		}
		command, found := registry.Find(args[:2])
		if !found {
			return invocation{}, root, invalidInvocation("unsupported %s action %q", root, args[1])
		}
		if len(args) == 3 && (args[2] == "--help" || args[2] == "-h") {
			return invocation{}, command.Name(), nil
		}
		return invocation{command: command, args: args[2:]}, "", nil
	}
	command, found := registry.Find(args[:1])
	if !found {
		return invocation{}, "root", invalidInvocation("unsupported admin command %q", root)
	}
	if len(args) == 2 && (args[1] == "--help" || args[1] == "-h") {
		return invocation{}, command.Name(), nil
	}
	return invocation{command: command, args: args[1:]}, "", nil
}

func parseCommandOptions(command *Command, args []string) (Values, *CLIError) {
	specs := make(map[string]OptionSpec, len(command.Options))
	for _, spec := range command.Options {
		specs[spec.Name] = spec
	}
	values := Values{}
	seen := map[string]bool{}
	positionals := []string{}
	for index := 0; index < len(args); index++ {
		token := args[index]
		if token == "--" {
			positionals = append(positionals, args[index+1:]...)
			break
		}
		name, inline, hasInline := splitLongOption(token)
		if name == "" {
			positionals = append(positionals, token)
			continue
		}
		spec, exists := specs[name]
		if !exists {
			return nil, invalidInvocation("%s does not support --%s", command.Name(), name)
		}
		if seen[name] {
			return nil, invalidInvocation("--%s may be specified only once", name)
		}
		seen[name] = true
		switch spec.Kind {
		case BooleanOption:
			value := true
			if hasInline {
				parsed, err := strconv.ParseBool(inline)
				if err != nil {
					return nil, invalidInvocation("--%s requires true or false", name)
				}
				value = parsed
			}
			values[name] = value
		case IntegerOption:
			value, next, err := optionValue(name, inline, hasInline, args, index)
			if err != nil {
				return nil, err
			}
			index = next
			parsed, parseErr := strconv.Atoi(value)
			if parseErr != nil || spec.Positive && parsed <= 0 {
				qualifier := "an integer"
				if spec.Positive {
					qualifier = "a positive integer"
				}
				return nil, invalidInvocation("--%s requires %s", name, qualifier)
			}
			values[name] = parsed
		case StringOption:
			value, next, err := optionValue(name, inline, hasInline, args, index)
			if err != nil {
				return nil, err
			}
			index = next
			if strings.TrimSpace(value) == "" {
				return nil, invalidInvocation("--%s requires a non-empty value", name)
			}
			if len(spec.Choices) > 0 && !contains(spec.Choices, value) {
				return nil, invalidInvocation("--%s must be one of %s", name, strings.Join(spec.Choices, ", "))
			}
			values[name] = value
		}
	}
	if len(positionals) > len(command.Arguments) {
		return nil, invalidInvocation("%s accepts no positional argument %q", command.Name(), positionals[len(command.Arguments)])
	}
	for index, spec := range command.Arguments {
		if index >= len(positionals) {
			if spec.Required {
				return nil, invalidInvocation("%s requires <%s>", command.Name(), spec.Name)
			}
			continue
		}
		value := positionals[index]
		if strings.TrimSpace(value) == "" {
			return nil, invalidInvocation("argument <%s> requires a non-empty value", spec.Name)
		}
		if len(spec.Choices) > 0 && !contains(spec.Choices, value) {
			return nil, invalidInvocation("argument <%s> must be one of %s", spec.Name, strings.Join(spec.Choices, ", "))
		}
		values[spec.Name] = value
	}
	for _, spec := range command.Options {
		if spec.Required {
			if _, exists := values[spec.Name]; !exists {
				return nil, invalidInvocation("%s requires --%s", command.Name(), spec.Name)
			}
		}
		if _, exists := values[spec.Name]; !exists && spec.DefaultText != "" {
			switch spec.Kind {
			case StringOption:
				values[spec.Name] = spec.DefaultText
			case BooleanOption:
				values[spec.Name] = spec.DefaultText == "true"
			case IntegerOption:
				parsed, _ := strconv.Atoi(spec.DefaultText)
				values[spec.Name] = parsed
			}
		}
	}
	if command.Validate != nil {
		if err := command.Validate(values); err != nil {
			return nil, invalidInvocation("%s", err)
		}
	}
	return values, nil
}

func optionValue(name, inline string, hasInline bool, args []string, index int) (string, int, *CLIError) {
	if hasInline {
		return inline, index, nil
	}
	next := index + 1
	if next >= len(args) || strings.HasPrefix(args[next], "--") {
		return "", index, invalidInvocation("--%s requires a value", name)
	}
	return args[next], next, nil
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func requireExactlyOne(values Values, names ...string) error {
	count := 0
	for _, name := range names {
		if value, exists := values[name]; exists {
			switch typed := value.(type) {
			case string:
				if strings.TrimSpace(typed) != "" {
					count++
				}
			case int:
				if typed != 0 {
					count++
				}
			default:
				count++
			}
		}
	}
	if count != 1 {
		return fmt.Errorf("exactly one of --%s is required", strings.Join(names, " or --"))
	}
	return nil
}
