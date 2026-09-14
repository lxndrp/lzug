package admincli

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const defaultAdminEndpoint = "unix:///run/lzug-admin/admin.sock"

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
	config := EffectiveConfig{}
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
			for key, value := range parsed {
				setTargetValue(&config, key, value, "file")
			}
		}
	}

	for key, name := range targetEnvironment {
		if value, exists := environment[name]; exists {
			setTargetValue(&config, key, value, name)
		}
	}
	for key, value := range global.TargetValues {
		setTargetValue(&config, key, value, "flag")
	}

	if failure := validateTarget(config); failure != nil {
		return EffectiveConfig{}, failure
	}
	if config.target("endpoint") == "" {
		setTargetValue(&config, "endpoint", defaultAdminEndpoint, "default")
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
		if targetEnvironment[key] == "" {
			if key == "container" {
				return nil, fmt.Errorf("The configuration key %q was removed; use %q instead.", key, "endpoint")
			}
			return nil, fmt.Errorf("The CLI configuration contains an unsupported key.")
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
		isTarget := false
		for _, variable := range targetEnvironment {
			isTarget = isTarget || name == variable
		}
		if name == "LZUG_ADMIN_CONTAINER" || isTarget {
			if name == "LZUG_ADMIN_CONTAINER" {
				return nil, legacyContainerError(name)
			}
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

func legacyContainerError(source string) *CLIError {
	return &CLIError{Class: "configuration_error", Message: fmt.Sprintf("%s was removed; the CLI no longer selects containers. Use --endpoint or LZUG_ADMIN_ENDPOINT for the running admin socket.", source), NextStep: "Use unix:///run/lzug-admin/admin.sock or another explicit supported local endpoint.", ExitCode: ExitConfiguration}
}

func configurationError(message string) *CLIError {
	return &CLIError{
		Class:    "configuration_error",
		Message:  message,
		NextStep: "Use only documented non-secret target settings, or pass --no-config with explicit target options.",
		ExitCode: ExitConfiguration,
	}
}
