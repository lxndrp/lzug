package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestVersionTextUsesBuildMetadata(t *testing.T) {
	previous := applicationVersion
	applicationVersion = "1.2.3"
	t.Cleanup(func() { applicationVersion = previous })
	if got := versionText(); got != "lzug-admin 1.2.3" {
		t.Fatalf("unexpected version text %q", got)
	}
}

func TestCanonicalBuildMetadataUsesLinkedIdentity(t *testing.T) {
	previousVersion := applicationVersion
	previousRevision := applicationRevision
	previousTag := applicationTag
	applicationVersion = "1.2.3-rc.1"
	applicationRevision = strings.Repeat("a", 40)
	applicationTag = "v1.2.3-rc.1"
	t.Cleanup(func() {
		applicationVersion = previousVersion
		applicationRevision = previousRevision
		applicationTag = previousTag
	})

	encoded, err := json.Marshal(cliBuildMetadata())
	if err != nil {
		t.Fatal(err)
	}
	expected := `{"identity":"1.2.3-rc.1","release":true,"revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","tag":"v1.2.3-rc.1"}`
	if string(encoded) != expected {
		t.Fatalf("unexpected build metadata %s", encoded)
	}
}
