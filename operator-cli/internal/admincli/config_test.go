package admincli

import (
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"
)

func TestConfigurationPriorityIsFlagEnvironmentFileDefault(t *testing.T) {
	resolver := &SystemConfigResolver{
		Environment: func() []string {
			return []string{"LZUG_ADMIN_ENDPOINT=tcp://127.0.0.1:1235"}
		},
		UserConfigDir: func() (string, error) { return "/configuration", nil },
		ReadFile: func(path string) ([]byte, error) {
			if path != "/configuration/lzug/admin.json" {
				t.Fatalf("unexpected config path %q", path)
			}
			return []byte(`{"endpoint":"tcp://127.0.0.1:1234"}`), nil
		},
	}
	config, failure := resolver.Resolve(GlobalOptions{})
	if failure != nil {
		t.Fatal(failure)
	}
	want := EffectiveConfig{}
	setTargetValue(&want, "endpoint", "tcp://127.0.0.1:1235", "LZUG_ADMIN_ENDPOINT")
	if !reflect.DeepEqual(config, want) {
		t.Fatalf("unexpected effective config: %#v", config)
	}
	config, failure = resolver.Resolve(GlobalOptions{TargetValues: map[string]string{"endpoint": "tcp://127.0.0.1:1236"}})
	if failure != nil {
		t.Fatal(failure)
	}
	want = EffectiveConfig{}
	setTargetValue(&want, "endpoint", "tcp://127.0.0.1:1236", "flag")
	if !reflect.DeepEqual(config, want) {
		t.Fatalf("unexpected flag config: %#v", config)
	}
}

func TestMissingDefaultConfigIsAllowedButExplicitConfigFails(t *testing.T) {
	resolver := &SystemConfigResolver{
		Environment:   func() []string { return nil },
		UserConfigDir: func() (string, error) { return "/configuration", nil },
		ReadFile:      func(string) ([]byte, error) { return nil, os.ErrNotExist },
	}
	config, failure := resolver.Resolve(GlobalOptions{})
	if failure != nil {
		t.Fatal(failure)
	}
	if config.target("endpoint") != defaultAdminEndpoint || config.Target["endpoint"].Source != "default" {
		t.Fatalf("unexpected defaults: %#v", config)
	}
	_, failure = resolver.Resolve(GlobalOptions{ConfigPath: "/missing.json", ConfigSet: true})
	if failure == nil || failure.ExitCode != ExitConfiguration {
		t.Fatalf("missing explicit config did not fail safely: %#v", failure)
	}
}

func TestNoConfigSkipsFileAndUsesEnvironment(t *testing.T) {
	resolver := &SystemConfigResolver{
		Environment: func() []string { return []string{"LZUG_ADMIN_ENDPOINT=tcp://127.0.0.1:1234"} },
		UserConfigDir: func() (string, error) {
			return "", errors.New("must not be called")
		},
		ReadFile: func(string) ([]byte, error) {
			t.Fatal("configuration file was read with --no-config")
			return nil, nil
		},
	}
	config, failure := resolver.Resolve(GlobalOptions{NoConfig: true})
	if failure != nil {
		t.Fatal(failure)
	}
	if config.target("endpoint") != "tcp://127.0.0.1:1234" {
		t.Fatalf("unexpected no-config result: %#v", config)
	}
}

func TestConfigurationRejectsSecretsConfirmationsAndInvalidFiles(t *testing.T) {
	for _, environment := range [][]string{
		{"LZUG_ADMIN_TOKEN=secret-marker"},
		{"LZUG_ADMIN_FORCE=true"},
		{"LZUG_ADMIN_VERBOSE=true"},
	} {
		resolver := &SystemConfigResolver{
			Environment:   func() []string { return environment },
			UserConfigDir: func() (string, error) { return "/configuration", nil },
			ReadFile:      func(string) ([]byte, error) { return nil, os.ErrNotExist },
		}
		if _, failure := resolver.Resolve(GlobalOptions{}); failure == nil {
			t.Fatalf("forbidden environment was accepted: %q", environment)
		}
	}
	for _, payload := range []string{
		`{"token":"secret-marker"}`,
		`{"force":true}`,
		`{"json":true}`,
		`{"engine":"docker"}`,
		`{"container":"lzug"}`,
		`[]`,
		`{"container":"lzug"} {"container":"other"}`,
	} {
		resolver := &SystemConfigResolver{
			Environment:   func() []string { return nil },
			UserConfigDir: func() (string, error) { return "/configuration", nil },
			ReadFile:      func(string) ([]byte, error) { return []byte(payload), nil },
		}
		if _, failure := resolver.Resolve(GlobalOptions{}); failure == nil {
			t.Fatalf("invalid configuration was accepted: %s", payload)
		}
	}
}

func TestRemovedContainerSourcesFailBeforeTransport(t *testing.T) {
	for _, test := range []struct {
		name        string
		environment []string
		file        []byte
	}{
		{name: "environment", environment: []string{"LZUG_ADMIN_CONTAINER=legacy"}},
		{name: "file", file: []byte(`{"container":"legacy"}`)},
	} {
		t.Run(test.name, func(t *testing.T) {
			resolver := &SystemConfigResolver{
				Environment:   func() []string { return test.environment },
				UserConfigDir: func() (string, error) { return "/configuration", nil },
				ReadFile:      func(string) ([]byte, error) { return test.file, nil },
			}
			if test.file == nil {
				resolver.ReadFile = func(string) ([]byte, error) { return nil, os.ErrNotExist }
			}
			if _, failure := resolver.Resolve(GlobalOptions{}); failure == nil || failure.ExitCode != ExitConfiguration || !strings.Contains(failure.Message, "removed") {
				t.Fatalf("legacy source was not rejected with migration guidance: %#v", failure)
			}
		})
	}
}
