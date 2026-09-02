package admincli

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var containerNamePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`)

type SystemConfigResolver struct {
	Environment   func() []string
	UserConfigDir func() (string, error)
	ReadFile      func(string) ([]byte, error)
}

func NewSystemConfigResolver() *SystemConfigResolver {
	return &SystemConfigResolver{
		Environment:   os.Environ,
		UserConfigDir: os.UserConfigDir,
		ReadFile:      os.ReadFile,
	}
}

func (r *SystemConfigResolver) Resolve(global GlobalOptions) (EffectiveConfig, *CLIError) {
	config := EffectiveConfig{
		Engine:    EffectiveValue{Value: "auto", Source: "default"},
		Container: EffectiveValue{Value: "", Source: "default"},
	}
	environment, environmentError := allowedEnvironment(r.Environment())
	if environmentError != nil {
		return EffectiveConfig{}, environmentError
	}

	if !global.NoConfig {
		path := global.ConfigPath
		explicit := global.ConfigSet
		if path == "" {
			directory, err := r.UserConfigDir()
			if err != nil {
				return EffectiveConfig{}, configurationError("The default configuration location is unavailable.")
			}
			path = filepath.Join(directory, "lzug", "admin.json")
		}
		fileValues, err := r.ReadFile(path)
		if err != nil {
			if explicit || !errors.Is(err, os.ErrNotExist) {
				return EffectiveConfig{}, configurationError("The requested CLI configuration file could not be read.")
			}
		} else {
			parsed, parseErr := parseConfigFile(fileValues)
			if parseErr != nil {
				return EffectiveConfig{}, configurationError(parseErr.Error())
			}
			if value, exists := parsed["engine"]; exists {
				config.Engine = EffectiveValue{Value: value, Source: "file"}
			}
			if value, exists := parsed["container"]; exists {
				config.Container = EffectiveValue{Value: value, Source: "file"}
			}
		}
	}

	if value, exists := environment["LZUG_ADMIN_ENGINE"]; exists {
		config.Engine = EffectiveValue{Value: value, Source: "LZUG_ADMIN_ENGINE"}
	}
	if value, exists := environment["LZUG_ADMIN_CONTAINER"]; exists {
		config.Container = EffectiveValue{Value: value, Source: "LZUG_ADMIN_CONTAINER"}
	}
	if global.EngineSet {
		config.Engine = EffectiveValue{Value: global.Engine, Source: "flag"}
	}
	if global.ContainerSet {
		config.Container = EffectiveValue{Value: global.Container, Source: "flag"}
	}

	if !contains([]string{"auto", "docker", "podman"}, config.Engine.Value) {
		return EffectiveConfig{}, configurationError("The effective engine must be auto, docker, or podman.")
	}
	if config.Container.Value != "" && !containerNamePattern.MatchString(config.Container.Value) {
		return EffectiveConfig{}, configurationError("The effective container must be a valid exact container name.")
	}
	return config, nil
}

func parseConfigFile(payload []byte) (map[string]string, error) {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	var raw map[string]json.RawMessage
	if err := decoder.Decode(&raw); err != nil || raw == nil {
		return nil, fmt.Errorf("The CLI configuration file must contain one JSON object.")
	}
	if err := ensureJSONEnd(decoder); err != nil {
		return nil, fmt.Errorf("The CLI configuration file must contain exactly one JSON object.")
	}
	keys := make([]string, 0, len(raw))
	for key := range raw {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	values := map[string]string{}
	for _, key := range keys {
		if key != "engine" && key != "container" {
			return nil, fmt.Errorf("Configuration key %q is not allowed; only engine and container are supported.", key)
		}
		var value string
		if err := json.Unmarshal(raw[key], &value); err != nil || strings.TrimSpace(value) == "" {
			return nil, fmt.Errorf("Configuration key %q must be a non-empty string.", key)
		}
		values[key] = value
	}
	return values, nil
}

func ensureJSONEnd(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return fmt.Errorf("additional JSON value")
		}
		return err
	}
	return nil
}

func allowedEnvironment(entries []string) (map[string]string, *CLIError) {
	allowed := map[string]string{}
	for _, entry := range entries {
		name, value, found := strings.Cut(entry, "=")
		if !found || !strings.HasPrefix(name, "LZUG_ADMIN_") {
			continue
		}
		if name == "LZUG_ADMIN_ENGINE" || name == "LZUG_ADMIN_CONTAINER" {
			if strings.TrimSpace(value) == "" {
				return nil, configurationError(fmt.Sprintf("Environment variable %s must not be empty.", name))
			}
			allowed[name] = value
			continue
		}
		upper := strings.ToUpper(name)
		for _, forbidden := range []string{
			"SECRET", "TOKEN", "PASSWORD", "PASSPHRASE", "PRIVATE_KEY",
			"RECIPIENT", "FORCE", "CONFIRM", "VERBOSE", "JSON",
		} {
			if strings.Contains(upper, forbidden) {
				return nil, configurationError(fmt.Sprintf("Environment variable %s is not an allowed CLI configuration source.", name))
			}
		}
	}
	return allowed, nil
}

func configurationError(message string) *CLIError {
	return &CLIError{
		Class:    "configuration_error",
		Message:  message,
		NextStep: "Use only engine and container in the CLI configuration, or pass --no-config.",
		ExitCode: ExitConfiguration,
	}
}
