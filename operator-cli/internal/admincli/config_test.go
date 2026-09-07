package admincli

import (
	"errors"
	"os"
	"reflect"
	"testing"
)

func TestConfigurationPriorityIsFlagEnvironmentFileDefault(t *testing.T) {
	resolver := &SystemConfigResolver{
		Environment: func() []string {
			return []string{"LZUG_ADMIN_CONTAINER=from-environment"}
		},
		UserConfigDir: func() (string, error) { return "/configuration", nil },
		ReadFile: func(path string) ([]byte, error) {
			if path != "/configuration/lzug/admin.json" {
				t.Fatalf("unexpected config path %q", path)
			}
			return []byte(`{"container":"from-file"}`), nil
		},
	}
	config, failure := resolver.Resolve(GlobalOptions{})
	if failure != nil {
		t.Fatal(failure)
	}
	want := EffectiveConfig{Container: EffectiveValue{Value: "from-environment", Source: "LZUG_ADMIN_CONTAINER"}}
	if !reflect.DeepEqual(config, want) {
		t.Fatalf("unexpected effective config: %#v", config)
	}
	config, failure = resolver.Resolve(GlobalOptions{Container: "from-flag", ContainerSet: true})
	if failure != nil {
		t.Fatal(failure)
	}
	want = EffectiveConfig{Container: EffectiveValue{Value: "from-flag", Source: "flag"}}
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
	if config.Container.Value != "" || config.Container.Source != "default" {
		t.Fatalf("unexpected defaults: %#v", config)
	}
	_, failure = resolver.Resolve(GlobalOptions{ConfigPath: "/missing.json", ConfigSet: true})
	if failure == nil || failure.ExitCode != ExitConfiguration {
		t.Fatalf("missing explicit config did not fail safely: %#v", failure)
	}
}

func TestNoConfigSkipsFileAndUsesEnvironment(t *testing.T) {
	resolver := &SystemConfigResolver{
		Environment: func() []string { return []string{"LZUG_ADMIN_CONTAINER=lzug"} },
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
	if config.Container != (EffectiveValue{Value: "lzug", Source: "LZUG_ADMIN_CONTAINER"}) {
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
		`{"container":"../lzug"}`,
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
