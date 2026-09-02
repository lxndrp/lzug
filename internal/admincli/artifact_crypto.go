package admincli

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"

	"filippo.io/age"
)

const (
	artifactMagic       = "LZUGA02\n"
	legacyArtifactMagic = "LZUGA01\n"
	artifactFormat      = "lzug-age-artifact"
	artifactVersion     = 2
	artifactProtection  = "age-x25519-v1"
	maxArtifactHeader   = 16 * 1024
	maxIdentityBytes    = 16 * 1024
)

type artifactHeader struct {
	Format                  string `json:"format"`
	FormatVersion           int    `json:"format_version"`
	Protection              string `json:"protection"`
	RecipientKeyFingerprint string `json:"recipient_key_fingerprint"`
}

func parseRecipient(value string) (*age.X25519Recipient, string, error) {
	recipient, err := age.ParseX25519Recipient(strings.TrimSpace(value))
	if err != nil {
		return nil, "", artifactLocalError("recipient_key_invalid", "The age recipient is invalid.", ExitInvalidInvocation)
	}
	canonical := recipient.String()
	return recipient, recipientFingerprint(canonical), nil
}

func parseIdentity(value string) (*age.X25519Identity, string, string, error) {
	identity, err := age.ParseX25519Identity(strings.TrimSpace(value))
	if err != nil {
		return nil, "", "", artifactLocalError("recipient_key_invalid", "The age identity is invalid.", ExitInvalidInvocation)
	}
	recipient := identity.Recipient().String()
	return identity, recipient, recipientFingerprint(recipient), nil
}

func recipientFingerprint(recipient string) string {
	sum := sha256.Sum256([]byte(recipient))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func generateRecipientKeypair(identityPath, recipientPath string) (map[string]any, *CLIError) {
	identity, err := age.GenerateX25519Identity()
	if err != nil {
		return nil, unexpectedError()
	}
	identityValue := []byte(identity.String() + "\n")
	recipientValue := []byte(identity.Recipient().String() + "\n")
	if err := atomicPair(identityPath, identityValue, recipientPath, recipientValue); err != nil {
		return nil, artifactLocalError("key_write_failed", "Recipient key files could not be created atomically.", ExitUnexpected)
	}
	fingerprint := recipientFingerprint(identity.Recipient().String())
	return map[string]any{
		"protection":      artifactProtection,
		"recipient":       identity.Recipient().String(),
		"fingerprint":     fingerprint,
		"identity_file":   identityPath,
		"recipient_file":  recipientPath,
		"backup_required": true,
	}, nil
}

func inspectKeyFile(path string) (map[string]any, *CLIError) {
	content, err := os.ReadFile(path)
	if err != nil || len(content) > maxIdentityBytes {
		return nil, artifactLocalError("key_file_unreadable", "The recipient key file cannot be read.", ExitInvalidInvocation)
	}
	if identity, recipient, fingerprint, parseErr := parseIdentity(string(content)); parseErr == nil {
		if err := verifyPrivateFile(path); err != nil {
			return nil, artifactLocalError("key_file_unsafe", "The private identity file has unsafe ownership or permissions.", ExitInvalidInvocation)
		}
		_ = identity
		return map[string]any{
			"protection":       artifactProtection,
			"recipient":        recipient,
			"fingerprint":      fingerprint,
			"public_derivable": true,
			"private":          true,
		}, nil
	}
	recipient, fingerprint, parseErr := parseRecipient(string(content))
	if parseErr != nil {
		return nil, parseErr.(*CLIError)
	}
	return map[string]any{
		"protection":       artifactProtection,
		"recipient":        recipient.String(),
		"fingerprint":      fingerprint,
		"public_derivable": false,
		"private":          false,
	}, nil
}

func loadIdentity(input Input, values Values) (*age.X25519Identity, string, string, *CLIError) {
	sources := 0
	for _, name := range []string{"identity-file", "identity-stdin", "identity-prompt"} {
		if values.String(name) != "" || values.Bool(name) {
			sources++
		}
	}
	if sources != 1 {
		return nil, "", "", invalidInvocation("exactly one of --identity-file, --identity-stdin, or --identity-prompt is required")
	}
	var value string
	if path := values.String("identity-file"); path != "" {
		if err := verifyPrivateFile(path); err != nil {
			return nil, "", "", artifactLocalError("key_file_unsafe", "The private identity file has unsafe ownership or permissions.", ExitInvalidInvocation)
		}
		content, err := os.ReadFile(path)
		if err != nil || len(content) > maxIdentityBytes {
			return nil, "", "", artifactLocalError("key_file_unreadable", "The private identity file cannot be read.", ExitInvalidInvocation)
		}
		value = string(content)
	} else {
		if values.Bool("identity-prompt") && !input.IsTerminal() {
			return nil, "", "", invalidInvocation("--identity-prompt requires an interactive terminal")
		}
		if values.Bool("identity-stdin") && input.IsTerminal() {
			return nil, "", "", invalidInvocation("--identity-stdin requires redirected standard input")
		}
		secret, err := input.ReadSecret("Private age identity")
		if err != nil {
			return nil, "", "", artifactLocalError("key_input_failed", "The private identity could not be read.", ExitInvalidInvocation)
		}
		value = secret
	}
	identity, recipient, fingerprint, err := parseIdentity(value)
	if err != nil {
		return nil, "", "", err.(*CLIError)
	}
	return identity, recipient, fingerprint, nil
}

func identitySelfTest(identity *age.X25519Identity) error {
	var encrypted bytes.Buffer
	writer, err := age.Encrypt(&encrypted, identity.Recipient())
	if err != nil {
		return err
	}
	if _, err = writer.Write([]byte("lzug-recipient-possession")); err != nil {
		return err
	}
	if err = writer.Close(); err != nil {
		return err
	}
	reader, err := age.Decrypt(bytes.NewReader(encrypted.Bytes()), identity)
	if err != nil {
		return err
	}
	plain, err := io.ReadAll(reader)
	if err != nil || string(plain) != "lzug-recipient-possession" {
		return errors.New("recipient self-test failed")
	}
	return nil
}

func writeProtectedArtifact(
	ctx context.Context,
	path string,
	recipient *age.X25519Recipient,
	fingerprint string,
	produce func(io.Writer) (BackendResponse, int, error),
) (BackendResponse, int, *CLIError) {
	if _, err := os.Lstat(path); !errors.Is(err, os.ErrNotExist) {
		return BackendResponse{}, ExitInvalidInvocation, artifactLocalError("target_exists", "The target artifact already exists.", ExitInvalidInvocation)
	}
	directory := filepath.Dir(path)
	temporary, err := os.CreateTemp(directory, ".lzug-age-*.tmp")
	if err != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("artifact_write_failed", "The protected temporary artifact cannot be created.", ExitUnexpected)
	}
	temporaryPath := temporary.Name()
	published := false
	defer func() {
		_ = temporary.Close()
		if !published {
			_ = os.Remove(temporaryPath)
		}
	}()
	if err = temporary.Chmod(0o600); err != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("artifact_write_failed", "The protected temporary artifact cannot be secured.", ExitUnexpected)
	}
	header := artifactHeader{artifactFormat, artifactVersion, artifactProtection, fingerprint}
	encoded, _ := json.Marshal(header)
	if len(encoded) > maxArtifactHeader {
		return BackendResponse{}, ExitUnexpected, unexpectedError()
	}
	if _, err = temporary.WriteString(artifactMagic); err == nil {
		err = binary.Write(temporary, binary.BigEndian, uint32(len(encoded)))
	}
	if err == nil {
		_, err = temporary.Write(encoded)
	}
	if err != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("artifact_write_failed", "The protected artifact preamble cannot be written.", ExitUnexpected)
	}
	ageWriter, err := age.Encrypt(temporary, recipient)
	if err != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("encryption_failed", "The age stream could not be initialized.", ExitUnexpected)
	}
	response, exitCode, transportErr := produce(ageWriter)
	closeErr := ageWriter.Close()
	if transportErr != nil {
		return BackendResponse{}, exitCode, runtimeFailure(transportErr)
	}
	if closeErr != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("encryption_failed", "The age stream could not be finalized.", ExitUnexpected)
	}
	if !response.OK {
		return response, exitCode, backendCLIError(response, exitCode)
	}
	if err = temporary.Sync(); err != nil || temporary.Close() != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("artifact_write_failed", "The protected artifact could not be synchronized.", ExitUnexpected)
	}
	if err = os.Link(temporaryPath, path); err != nil {
		return BackendResponse{}, ExitUnexpected, artifactLocalError("artifact_activation_failed", "The protected artifact could not be activated without overwrite.", ExitUnexpected)
	}
	published = true
	_ = os.Remove(temporaryPath)
	_ = ctx
	return response, exitCode, nil
}

func consumeProtectedArtifact(
	path string,
	identity *age.X25519Identity,
	fingerprint string,
	consume func(io.Reader) (BackendResponse, int, error),
) (BackendResponse, int, *CLIError) {
	source, err := os.Open(path)
	if err != nil {
		return BackendResponse{}, ExitInvalidInvocation, artifactLocalError("artifact_unreadable", "The protected artifact cannot be read.", ExitInvalidInvocation)
	}
	defer source.Close()
	buffered := bufio.NewReader(source)
	header, err := readArtifactHeader(buffered)
	if err != nil {
		return BackendResponse{}, ExitInvalidInvocation, err.(*CLIError)
	}
	if header.RecipientKeyFingerprint != fingerprint {
		return BackendResponse{}, ExitInvalidInvocation, artifactLocalError("recipient_key_mismatch", "The identity does not match the artifact fingerprint.", ExitInvalidInvocation)
	}
	plain, decryptErr := age.Decrypt(buffered, identity)
	if decryptErr != nil {
		return BackendResponse{}, ExitInvalidInvocation, artifactLocalError("artifact_integrity_failed", "The age artifact cannot be decrypted.", ExitInvalidInvocation)
	}
	verified := &integrityReader{source: plain}
	response, exitCode, transportErr := consume(verified)
	if verified.err != nil {
		return BackendResponse{}, ExitInvalidInvocation, artifactLocalError("artifact_integrity_failed", "The age artifact cannot be decrypted.", ExitInvalidInvocation)
	}
	if transportErr != nil {
		return BackendResponse{}, exitCode, runtimeFailure(transportErr)
	}
	if !response.OK {
		return response, exitCode, backendCLIError(response, exitCode)
	}
	return response, exitCode, nil
}

type integrityReader struct {
	source io.Reader
	err    error
}

func (reader *integrityReader) Read(buffer []byte) (int, error) {
	count, err := reader.source.Read(buffer)
	if err != nil && !errors.Is(err, io.EOF) {
		reader.err = err
	}
	return count, err
}

func inspectArtifact(path string) (map[string]any, *CLIError) {
	source, err := os.Open(path)
	if err != nil {
		return nil, artifactLocalError("artifact_unreadable", "The protected artifact cannot be read.", ExitInvalidInvocation)
	}
	defer source.Close()
	header, err := readArtifactHeader(bufio.NewReader(source))
	if err != nil {
		return nil, err.(*CLIError)
	}
	return map[string]any{
		"format":                    header.Format,
		"format_version":            header.FormatVersion,
		"protection":                header.Protection,
		"recipient_key_fingerprint": header.RecipientKeyFingerprint,
	}, nil
}

func readArtifactHeader(source *bufio.Reader) (artifactHeader, error) {
	magic := make([]byte, len(artifactMagic))
	if _, err := io.ReadFull(source, magic); err != nil {
		return artifactHeader{}, artifactLocalError("artifact_preamble_invalid", "The artifact preamble is invalid.", ExitInvalidInvocation)
	}
	if string(magic) == legacyArtifactMagic {
		return artifactHeader{}, artifactLocalError("artifact_legacy_v1", "This v0.6.0 artifact requires the documented v0.6.0 restore and upgrade path.", ExitProtocolIncompatible)
	}
	if string(magic) != artifactMagic {
		return artifactHeader{}, artifactLocalError("artifact_preamble_invalid", "The artifact preamble is invalid.", ExitInvalidInvocation)
	}
	var length uint32
	if err := binary.Read(source, binary.BigEndian, &length); err != nil || length == 0 || length > maxArtifactHeader {
		return artifactHeader{}, artifactLocalError("artifact_preamble_invalid", "The artifact preamble is invalid.", ExitInvalidInvocation)
	}
	encoded := make([]byte, length)
	if _, err := io.ReadFull(source, encoded); err != nil {
		return artifactHeader{}, artifactLocalError("artifact_preamble_invalid", "The artifact preamble is invalid.", ExitInvalidInvocation)
	}
	var header artifactHeader
	if json.Unmarshal(encoded, &header) != nil || header.Format != artifactFormat || header.FormatVersion != artifactVersion || header.Protection != artifactProtection || !validFingerprint(header.RecipientKeyFingerprint) {
		return artifactHeader{}, artifactLocalError("artifact_preamble_invalid", "The artifact preamble is invalid.", ExitInvalidInvocation)
	}
	return header, nil
}

func validFingerprint(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != 71 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil
}

func atomicPair(identityPath string, identity []byte, recipientPath string, recipient []byte) error {
	if identityPath == recipientPath {
		return errors.New("key paths must differ")
	}
	if err := atomicNewFile(identityPath, identity, 0o600, true); err != nil {
		return err
	}
	if err := atomicNewFile(recipientPath, recipient, 0o644, false); err != nil {
		_ = os.Remove(identityPath)
		return err
	}
	return nil
}

func atomicNewFile(path string, content []byte, mode os.FileMode, private bool) error {
	if _, err := os.Lstat(path); !errors.Is(err, os.ErrNotExist) {
		return errors.New("target exists")
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".lzug-key-*.tmp")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if err = temporary.Chmod(mode); err == nil {
		_, err = temporary.Write(content)
	}
	if err == nil {
		err = temporary.Sync()
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if private {
		if err = securePrivateFile(name); err != nil {
			return err
		}
	}
	if err = os.Link(name, path); err != nil {
		return err
	}
	if private {
		return verifyPrivateFile(path)
	}
	return nil
}

func artifactLocalError(class, message string, exitCode int) *CLIError {
	return &CLIError{
		Class:    class,
		Message:  message,
		NextStep: "Inspect the named local file and retry only after correcting the reported condition.",
		ExitCode: exitCode,
		Phase:    "local-artifact",
	}
}

func backendCLIError(response BackendResponse, exitCode int) *CLIError {
	if response.Error == nil {
		return protocolFailure()
	}
	return &CLIError{
		Class:    response.Error.Class,
		Message:  response.Error.Message,
		NextStep: "Correct the reported backend condition and inspect the operation state before retrying.",
		ExitCode: exitCode,
		Phase:    response.Error.Phase,
	}
}

func decodeBackendResult(response BackendResponse) (map[string]any, *CLIError) {
	if !response.OK {
		return nil, backendCLIError(response, ExitUnexpected)
	}
	result := map[string]any{}
	if err := json.Unmarshal(response.Result, &result); err != nil {
		return nil, protocolFailure()
	}
	return result, nil
}

func ensureArtifactTransport(local LocalContext) (ArtifactTransport, *CLIError) {
	factory, ok := local.Runtime.(ArtifactRuntimeFactory)
	if !ok {
		return nil, unexpectedError()
	}
	return factory.ArtifactTransport(local.Config), nil
}

func artifactHuman(result map[string]any) string {
	if artifact, ok := result["artifact"].(string); ok {
		return artifact + "\n"
	}
	return ""
}
