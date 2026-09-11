package admincli

import (
	"fmt"
	"net"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"unicode"
)

var targetEnvironment = map[string]string{
	"endpoint": "LZUG_ADMIN_ENDPOINT", "target-name": "LZUG_ADMIN_TARGET_NAME",
}

func setTargetValue(config *EffectiveConfig, key, value, source string) {
	if config.Target == nil {
		config.Target = map[string]EffectiveValue{}
	}
	config.Target[key] = EffectiveValue{Value: value, Source: source}
}

func (config EffectiveConfig) target(key string) string { return config.Target[key].Value }

// Endpoint syntax is intentionally literal: no DNS, URL credentials, query
// options, percent expansion or shell evaluation. Only existing local endpoints.
func parseEndpoint(value string) (network, address string, err error) {
	invalid := fmt.Errorf("invalid local admin endpoint")
	if strings.ContainsFunc(value, unicode.IsControl) || strings.ContainsAny(value, "%?#") {
		return "", "", invalid
	}
	if path, ok := strings.CutPrefix(value, "unix://"); ok {
		if runtime.GOOS == "windows" || !filepath.IsAbs(path) {
			return "", "", invalid
		}
		return "unix", path, nil
	}
	if address, ok := strings.CutPrefix(value, "tcp://"); ok {
		host, port, err := net.SplitHostPort(address)
		if err != nil || host != "127.0.0.1" && host != "::1" {
			return "", "", invalid
		}
		number, err := strconv.Atoi(port)
		if err != nil || number < 1 || number > 65535 || strconv.Itoa(number) != port {
			return "", "", invalid
		}
		network := "tcp4"
		if host == "::1" {
			network = "tcp6"
		}
		return network, address, nil
	}
	return "", "", invalid
}

func validateTarget(config EffectiveConfig) *CLIError {
	endpoint := config.target("endpoint")
	if endpoint == "" && len(config.Target) == 0 {
		return nil // Transitional container selection is removed by #747.
	}
	if config.Container.Value != "" {
		return configurationError("An endpoint target cannot include a container target.")
	}
	if _, _, err := parseEndpoint(endpoint); err != nil {
		return configurationError("Use an absolute unix:///path endpoint or tcp://127.0.0.1:PORT (also tcp://[::1]:PORT).")
	}
	name := config.target("target-name")
	if len(name) > 128 || strings.ContainsFunc(name, unicode.IsControl) || name != strings.TrimSpace(name) {
		return configurationError("The non-secret target name must be at most 128 bytes without control characters or surrounding whitespace.")
	}
	return nil
}

func (config EffectiveConfig) targetDescription() string {
	if endpoint := config.target("endpoint"); endpoint != "" {
		if name := config.target("target-name"); name != "" {
			return name + " (" + endpoint + ")"
		}
		return endpoint
	}
	return "container=" + config.Container.Value
}

func (config EffectiveConfig) hasTarget() bool {
	return config.target("endpoint") != "" || config.Container.Value != ""
}
