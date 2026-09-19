package admincli

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildMetadataReleaseContract(t *testing.T) {
	revision := strings.Repeat("a", 40)
	metadata := BuildMetadata(BuildInfo{Version: "1.2.3", Revision: revision, Tag: "v1.2.3"})
	encoded, err := json.Marshal(metadata)
	if err != nil {
		t.Fatal(err)
	}
	expected := `{"identity":"1.2.3","release":true,"revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","tag":"v1.2.3"}`
	if string(encoded) != expected {
		t.Fatalf("unexpected release build metadata %s", encoded)
	}
	if metadata.Release != true {
		t.Fatalf("release flag must be true for a tagged build")
	}
	if metadata.Tag == nil || *metadata.Tag != "v1.2.3" {
		t.Fatalf("tag must be carried for a tagged build")
	}
}

func TestBuildMetadataSnapshotContract(t *testing.T) {
	revision := strings.Repeat("b", 40)
	metadata := BuildMetadata(BuildInfo{Version: "0.0.0-dev+sha.1", Revision: revision, Tag: ""})
	encoded, err := json.Marshal(metadata)
	if err != nil {
		t.Fatal(err)
	}
	expected := `{"identity":"0.0.0-dev+sha.1","release":false,"revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","tag":null}`
	if string(encoded) != expected {
		t.Fatalf("unexpected snapshot build metadata %s", encoded)
	}
	if metadata.Release != false {
		t.Fatalf("release flag must be false for a snapshot build")
	}
	if metadata.Tag != nil {
		t.Fatalf("tag must stay null for a snapshot build")
	}
}

func TestBuildMetadataOptionRendersTheComponentContract(t *testing.T) {
	application, _, _, stdout, _ := testApplication(t, `{"version":1,"ok":true}`, 0)
	revision := strings.Repeat("c", 40)
	application.Build = BuildInfo{Version: "1.2.3-rc.1", Revision: revision, Tag: "v1.2.3-rc.1"}

	if code := application.Run(context.Background(), []string{"--build-metadata"}); code != ExitOK {
		t.Fatalf("--build-metadata returned %d", code)
	}
	expected := `{"identity":"1.2.3-rc.1","release":true,"revision":"cccccccccccccccccccccccccccccccccccccccc","tag":"v1.2.3-rc.1"}` + "\n"
	if stdout.String() != expected {
		t.Fatalf("--build-metadata rendered %q, want %q", stdout.String(), expected)
	}
}