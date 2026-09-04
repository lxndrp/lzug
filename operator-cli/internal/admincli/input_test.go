package admincli

import (
	"bufio"
	"bytes"
	"strings"
	"testing"
)

func TestConsoleInputConfirmsAtTerminalAndWritesOnlyThePrompt(t *testing.T) {
	stderr := &bytes.Buffer{}
	input := &ConsoleInput{
		reader:   bufio.NewReader(strings.NewReader("yes\n")),
		stderr:   stderr,
		terminal: true,
	}
	confirmed, err := input.Confirm("Disable account 7 and revoke all active sessions?")
	if err != nil || !confirmed {
		t.Fatalf("terminal confirmation failed: confirmed=%t error=%v", confirmed, err)
	}
	if stderr.String() != "Disable account 7 and revoke all active sessions? [y/N]: " {
		t.Fatalf("unexpected confirmation prompt %q", stderr.String())
	}
}

func TestConsoleInputReadsOneSecretWithoutWritingItsValue(t *testing.T) {
	stderr := &bytes.Buffer{}
	input := &ConsoleInput{
		stderr:   stderr,
		terminal: true,
		password: func() ([]byte, error) {
			return []byte("secret-marker"), nil
		},
	}
	secret, err := input.ReadSecret("One-time token")
	if err != nil || secret != "secret-marker" {
		t.Fatalf("terminal secret input failed: value=%q error=%v", secret, err)
	}
	if strings.Contains(stderr.String(), secret) || stderr.String() != "One-time token: \n" {
		t.Fatalf("secret reached program output: %q", stderr.String())
	}
}

func TestConsoleInputRejectsOversizedPipedSecret(t *testing.T) {
	input := &ConsoleInput{
		reader: bufio.NewReader(strings.NewReader(strings.Repeat("x", maxSecretInput+1))),
		stderr: &bytes.Buffer{},
	}
	if _, err := input.ReadSecret("One-time token"); err == nil {
		t.Fatal("oversized secret input was accepted")
	}
}
