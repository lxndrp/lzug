package admincli

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func successfulArtifactResponse(t *testing.T) BackendResponse {
	t.Helper()
	result, err := json.Marshal(map[string]any{"artifact_type": "backup", "verified": true})
	if err != nil {
		t.Fatal(err)
	}
	return BackendResponse{Version: ProtocolVersion, OK: true, Result: result}
}

func TestRecipientGenerationInspectionAndFingerprintContract(t *testing.T) {
	directory := t.TempDir()
	identityPath := filepath.Join(directory, "backup.agekey")
	recipientPath := filepath.Join(directory, "backup.agepub")
	result, failure := generateRecipientKeypair(identityPath, recipientPath)
	if failure != nil {
		t.Fatal(failure)
	}
	identityBytes, err := os.ReadFile(identityPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(string(identityBytes), "AGE-SECRET-KEY-1") {
		t.Fatal("identity is not an age X25519 identity")
	}
	if runtime.GOOS != "windows" {
		if mode := mustStat(t, identityPath).Mode().Perm(); mode != 0o600 {
			t.Fatalf("private mode is %o", mode)
		}
		if mode := mustStat(t, recipientPath).Mode().Perm(); mode != 0o644 {
			t.Fatalf("public mode is %o", mode)
		}
	}
	inspected, inspectFailure := inspectKeyFile(identityPath)
	if inspectFailure != nil {
		t.Fatal(inspectFailure)
	}
	if inspected["recipient"] != result["recipient"] || inspected["fingerprint"] != result["fingerprint"] {
		t.Fatalf("inspection mismatch: %#v %#v", inspected, result)
	}
	if strings.Contains(string(mustJSON(t, result)), "AGE-SECRET-KEY") {
		t.Fatal("result exposes the private identity")
	}
	known := "age1wkdx2jsjtg5wg2ts5ptcalmqvtdp9uwwplhl6yyraalr9g9l5gxqh4qu5t"
	if got := recipientFingerprint(known); got != "sha256:3cada6318fc58415acc7dae38ad884fc0eff82993aba4776e4274ac8e43700f7" {
		t.Fatalf("unexpected canonical fingerprint %q", got)
	}
}

func TestKeyGenerationNeverOverwritesAndCleansPartialPair(t *testing.T) {
	directory := t.TempDir()
	identityPath := filepath.Join(directory, "backup.agekey")
	recipientPath := filepath.Join(directory, "backup.agepub")
	if err := os.WriteFile(recipientPath, []byte("keep"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, failure := generateRecipientKeypair(identityPath, recipientPath); failure == nil {
		t.Fatal("expected existing-target failure")
	}
	if _, err := os.Stat(identityPath); !os.IsNotExist(err) {
		t.Fatal("partial private key was not removed")
	}
	if got := string(mustRead(t, recipientPath)); got != "keep" {
		t.Fatalf("existing target changed to %q", got)
	}
}

func TestAgeArtifactRoundTripInspectionTamperAndLegacyBoundary(t *testing.T) {
	directory := t.TempDir()
	identityPath := filepath.Join(directory, "backup.agekey")
	recipientPath := filepath.Join(directory, "backup.agepub")
	generated, failure := generateRecipientKeypair(identityPath, recipientPath)
	if failure != nil {
		t.Fatal(failure)
	}
	identity, _, fingerprint, parseFailure := parseIdentity(string(mustRead(t, identityPath)))
	if parseFailure != nil {
		t.Fatal(parseFailure)
	}
	recipient, _, recipientFailure := parseRecipient(string(mustRead(t, recipientPath)))
	if recipientFailure != nil {
		t.Fatal(recipientFailure)
	}
	artifact := filepath.Join(directory, "backup.lzug")
	payload := bytes.Repeat([]byte("streamed-clear-package"), 200_000)
	response, code, writeFailure := writeProtectedArtifact(
		context.Background(), artifact, recipient, fingerprint,
		func(target io.Writer) (BackendResponse, int, error) {
			_, err := target.Write(payload)
			return successfulArtifactResponse(t), 0, err
		},
	)
	if writeFailure != nil || code != 0 || !response.OK {
		t.Fatalf("write failed: %#v %d %#v", writeFailure, code, response)
	}
	metadata, inspectFailure := inspectArtifact(artifact)
	if inspectFailure != nil {
		t.Fatal(inspectFailure)
	}
	if metadata["recipient_key_fingerprint"] != generated["fingerprint"] || metadata["format_version"] != 2 {
		t.Fatalf("unexpected public preamble: %#v", metadata)
	}
	var clear bytes.Buffer
	_, code, consumeFailure := consumeProtectedArtifact(
		artifact, identity, fingerprint,
		func(source io.Reader) (BackendResponse, int, error) {
			_, err := clear.ReadFrom(source)
			return successfulArtifactResponse(t), 0, err
		},
	)
	if consumeFailure != nil || code != 0 || !bytes.Equal(clear.Bytes(), payload) {
		t.Fatalf("round trip failed: %#v %d", consumeFailure, code)
	}

	tampered := mustRead(t, artifact)
	tampered[len(tampered)-1] ^= 1
	tamperedPath := filepath.Join(directory, "tampered.lzug")
	if err := os.WriteFile(tamperedPath, tampered, 0o600); err != nil {
		t.Fatal(err)
	}
	_, _, consumeFailure = consumeProtectedArtifact(
		tamperedPath, identity, fingerprint,
		func(source io.Reader) (BackendResponse, int, error) {
			_, err := bytes.NewBuffer(nil).ReadFrom(source)
			return successfulArtifactResponse(t), 0, err
		},
	)
	if consumeFailure == nil || consumeFailure.Class != "artifact_integrity_failed" {
		t.Fatalf("tamper failure is %#v", consumeFailure)
	}

	legacyPath := filepath.Join(directory, "legacy.lzug")
	if err := os.WriteFile(legacyPath, []byte(legacyArtifactMagic+"legacy"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, legacyFailure := inspectArtifact(legacyPath)
	if legacyFailure == nil || legacyFailure.Class != "artifact_legacy_v1" || !strings.Contains(legacyFailure.Message, "v0.6.0") {
		t.Fatalf("legacy contract missing: %#v", legacyFailure)
	}
}

func TestIdentitySourcesAndUnsafeFileContract(t *testing.T) {
	directory := t.TempDir()
	identityPath := filepath.Join(directory, "backup.agekey")
	if _, failure := generateRecipientKeypair(identityPath, filepath.Join(directory, "backup.agepub")); failure != nil {
		t.Fatal(failure)
	}
	identityValue := strings.TrimSpace(string(mustRead(t, identityPath)))

	for name, testCase := range map[string]struct {
		input  *fakeInput
		values Values
	}{
		"file":   {&fakeInput{secrets: map[string]string{}}, Values{"identity-file": identityPath}},
		"stdin":  {&fakeInput{secrets: map[string]string{"Private age identity": identityValue}}, Values{"identity-stdin": true}},
		"prompt": {&fakeInput{terminal: true, secrets: map[string]string{"Private age identity": identityValue}}, Values{"identity-prompt": true}},
	} {
		t.Run(name, func(t *testing.T) {
			if _, _, _, failure := loadIdentity(testCase.input, testCase.values); failure != nil {
				t.Fatal(failure)
			}
		})
	}
	if _, _, _, failure := loadIdentity(&fakeInput{}, Values{}); failure == nil {
		t.Fatal("missing identity source accepted")
	}
	if runtime.GOOS != "windows" {
		if err := os.Chmod(identityPath, 0o644); err != nil {
			t.Fatal(err)
		}
		if _, _, _, failure := loadIdentity(&fakeInput{}, Values{"identity-file": identityPath}); failure == nil || failure.Class != "key_file_unsafe" {
			t.Fatalf("unsafe key accepted: %#v", failure)
		}
	}
}

func mustStat(t *testing.T, path string) os.FileInfo {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	return info
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	value, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return value
}

func mustJSON(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}
