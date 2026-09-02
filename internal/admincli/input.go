package admincli

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"golang.org/x/term"
)

const maxSecretInput = 512

var errInputInterrupted = errors.New("interactive input interrupted")

type terminalReadWriter struct {
	input       *os.File
	output      io.Writer
	interrupted bool
}

func (terminal *terminalReadWriter) Read(buffer []byte) (int, error) {
	count, err := terminal.input.Read(buffer)
	for _, value := range buffer[:count] {
		if value == 3 {
			terminal.interrupted = true
		}
	}
	return count, err
}

func (terminal *terminalReadWriter) Write(buffer []byte) (int, error) {
	return terminal.output.Write(buffer)
}

type ConsoleInput struct {
	stdin    *os.File
	reader   *bufio.Reader
	stderr   io.Writer
	terminal bool
	password func() ([]byte, error)
}

func NewConsoleInput(stdin *os.File, stderr io.Writer) *ConsoleInput {
	terminal := term.IsTerminal(int(stdin.Fd()))
	return &ConsoleInput{
		stdin:    stdin,
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

func (input *ConsoleInput) ReadLine(ctx context.Context, prompt string) (string, error) {
	if !input.terminal {
		return "", fmt.Errorf("dialog input requires an interactive terminal")
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	value, err := input.readTerminalLine(prompt, false)
	if errors.Is(err, errInputInterrupted) {
		return "", err
	}
	if err != nil && err != io.EOF {
		return "", fmt.Errorf("dialog input could not be read")
	}
	if err == io.EOF && value == "" {
		return "", io.EOF
	}
	return strings.TrimSpace(value), nil
}

func (input *ConsoleInput) Confirm(prompt string) (bool, error) {
	if !input.terminal {
		return false, fmt.Errorf("confirmation requires an interactive terminal")
	}
	if input.stdin == nil {
		_, _ = fmt.Fprintf(input.stderr, "%s [y/N]: ", prompt)
		answer, err := input.reader.ReadString('\n')
		if err != nil && err != io.EOF {
			return false, fmt.Errorf("confirmation input could not be read")
		}
		return confirmedAnswer(answer)
	}
	answer, err := input.readTerminalLine(prompt+" [y/N]: ", false)
	if errors.Is(err, errInputInterrupted) {
		return false, err
	}
	if err != nil && err != io.EOF {
		return false, fmt.Errorf("confirmation input could not be read")
	}
	return confirmedAnswer(answer)
}

func confirmedAnswer(answer string) (bool, error) {
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
		if input.stdin != nil {
			value, err := input.readTerminalLine(prompt+": ", true)
			if err != nil {
				return "", err
			}
			if len(value) > maxSecretInput {
				return "", fmt.Errorf("secret input is too large")
			}
			return validateSecret(value)
		}
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

func (input *ConsoleInput) readTerminalLine(prompt string, secret bool) (string, error) {
	if input.stdin == nil {
		return "", fmt.Errorf("terminal input is unavailable")
	}
	state, err := term.MakeRaw(int(input.stdin.Fd()))
	if err != nil {
		return "", fmt.Errorf("terminal input could not be initialized")
	}
	defer func() { _ = term.Restore(int(input.stdin.Fd()), state) }()

	readWriter := &terminalReadWriter{input: input.stdin, output: input.stderr}
	terminal := term.NewTerminal(readWriter, prompt)
	var value string
	if secret {
		value, err = terminal.ReadPassword(prompt)
	} else {
		value, err = terminal.ReadLine()
	}
	if readWriter.interrupted {
		_, _ = fmt.Fprintln(input.stderr, "^C")
		return "", errInputInterrupted
	}
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(value), nil
}

func validateSecret(value string) (string, error) {
	secret := strings.TrimSpace(value)
	if secret == "" || strings.ContainsAny(secret, "\r\n") {
		return "", fmt.Errorf("secret input is required as exactly one value")
	}
	return secret, nil
}
