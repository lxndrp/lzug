package admincli

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"strings"

	"golang.org/x/term"
)

const maxSecretInput = 512

type ConsoleInput struct {
	reader   *bufio.Reader
	stderr   io.Writer
	terminal bool
	password func() ([]byte, error)
}

func NewConsoleInput(stdin *os.File, stderr io.Writer) *ConsoleInput {
	terminal := false
	if info, err := stdin.Stat(); err == nil {
		terminal = info.Mode()&os.ModeCharDevice != 0
	}
	return &ConsoleInput{
		reader:   bufio.NewReader(stdin),
		stderr:   stderr,
		terminal: terminal,
		password: func() ([]byte, error) {
			return term.ReadPassword(int(stdin.Fd()))
		},
	}
}

func (input *ConsoleInput) IsTerminal() bool {
	return input.terminal
}

func (input *ConsoleInput) Confirm(prompt string) (bool, error) {
	if !input.terminal {
		return false, fmt.Errorf("confirmation requires an interactive terminal")
	}
	_, _ = fmt.Fprintf(input.stderr, "%s [y/N]: ", prompt)
	answer, err := input.reader.ReadString('\n')
	if err != nil && err != io.EOF {
		return false, fmt.Errorf("confirmation input could not be read")
	}
	switch strings.ToLower(strings.TrimSpace(answer)) {
	case "y", "yes":
		return true, nil
	case "", "n", "no":
		return false, nil
	default:
		return false, fmt.Errorf("confirmation must be yes or no")
	}
}

func (input *ConsoleInput) ReadSecret(prompt string) (string, error) {
	if input.terminal {
		_, _ = fmt.Fprintf(input.stderr, "%s: ", prompt)
		value, err := input.password()
		_, _ = fmt.Fprintln(input.stderr)
		if err != nil {
			return "", fmt.Errorf("secret input could not be read")
		}
		if len(value) > maxSecretInput {
			return "", fmt.Errorf("secret input is too large")
		}
		return validateSecret(string(value))
	}
	value, err := io.ReadAll(io.LimitReader(input.reader, maxSecretInput+1))
	if err != nil || len(value) > maxSecretInput {
		return "", fmt.Errorf("secret input is too large")
	}
	return validateSecret(string(value))
}

func validateSecret(value string) (string, error) {
	secret := strings.TrimSpace(value)
	if secret == "" || strings.ContainsAny(secret, "\r\n") {
		return "", fmt.Errorf("secret input is required as exactly one value")
	}
	return secret, nil
}
