package admincli

import (
	"bytes"
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

// This fixture launches the installed sshd with fresh synthetic keys and an
// isolated configuration on loopback. It never edits system/user SSH settings.
func externalSSHConfiguration(t *testing.T) (string, string) {
	t.Helper()
	if runtime.GOOS != "linux" {
		t.Skip("Linux target server fixture; native endpoint contracts run separately")
	}
	unavailable := func(reason string) {
		t.Helper()
		if os.Getenv("LZUG_TEST_OPENSSH_REQUIRED") == "1" {
			t.Fatal(reason)
		}
		t.Skip(reason)
	}
	sshd, err := exec.LookPath("sshd")
	if err != nil {
		sshd = "/usr/sbin/sshd"
		if _, err := os.Stat(sshd); err != nil {
			unavailable("system sshd unavailable")
		}
	}
	ssh, err := exec.LookPath("ssh")
	if err != nil {
		unavailable("system ssh unavailable")
	}
	keygen, err := exec.LookPath("ssh-keygen")
	if err != nil {
		unavailable("system ssh-keygen unavailable")
	}
	current, err := user.Current()
	if err != nil {
		t.Fatal(err)
	}
	// OpenSSH StrictModes rejects writable ancestors, including sticky /tmp.
	// Keep synthetic keys below the fixture user's private home, without
	// touching .ssh, authorized_keys or any existing host configuration.
	directory, err := os.MkdirTemp(current.HomeDir, ".lzug-ssh-test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(directory) })
	host := filepath.Join(directory, "host")
	client := filepath.Join(directory, "client")
	for _, path := range []string{host, client} {
		if err := exec.Command(keygen, "-q", "-t", "ed25519", "-N", "", "-f", path).Run(); err != nil {
			t.Fatal("cannot generate synthetic SSH fixture key", err)
		}
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	_ = listener.Close()
	serverConfig := filepath.Join(directory, "sshd_config")
	config := fmt.Sprintf("Port %d\nListenAddress 127.0.0.1\nHostKey %s\nPidFile %s\nAuthorizedKeysFile %s\nStrictModes yes\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\nAllowUsers %s\nAllowTcpForwarding local\nAllowStreamLocalForwarding local\nLogLevel VERBOSE\n", port, host, filepath.Join(directory, "pid"), client+".pub", current.Username)
	if err := os.WriteFile(serverConfig, []byte(config), 0600); err != nil {
		t.Fatal(err)
	}
	server := exec.Command(sshd, "-D", "-e", "-f", serverConfig)
	var logs bytes.Buffer
	server.Stderr = &logs
	if err := server.Start(); err != nil {
		unavailable("local sshd cannot start")
	}
	done := make(chan struct{})
	go func() { _ = server.Wait(); close(done) }()
	t.Cleanup(func() {
		_ = server.Process.Kill()
		<-done
		if t.Failed() {
			t.Log("Synthetic SSH server:", logs.String())
		}
	})
	deadline := time.Now().Add(3 * time.Second)
	for {
		select {
		case <-done:
			unavailable("local sshd fixture unavailable: " + logs.String())
		default:
		}
		connection, err := net.DialTimeout("tcp4", fmt.Sprintf("127.0.0.1:%d", port), 50*time.Millisecond)
		if err == nil {
			_ = connection.Close()
			break
		}
		if time.Now().After(deadline) {
			unavailable("local sshd fixture did not listen")
		}
		time.Sleep(10 * time.Millisecond)
	}
	hostKey, err := os.ReadFile(host + ".pub")
	if err != nil {
		t.Fatal(err)
	}
	known := filepath.Join(directory, "known_hosts")
	if err := os.WriteFile(known, []byte(fmt.Sprintf("[127.0.0.1]:%d %s", port, hostKey)), 0600); err != nil {
		t.Fatal(err)
	}
	clientConfig := filepath.Join(directory, "ssh_config")
	config = fmt.Sprintf("Host test-host\n HostName 127.0.0.1\n Port %d\n User %s\n IdentityFile %s\n IdentityAgent none\n IdentitiesOnly yes\n UserKnownHostsFile %s\n GlobalKnownHostsFile /dev/null\n", port, current.Username, client, known)
	if err := os.WriteFile(clientConfig, []byte(config), 0600); err != nil {
		t.Fatal(err)
	}
	return ssh, clientConfig
}

// Only the fixture owns OpenSSH. Product code receives the resulting endpoint,
// exactly as it would from an operator-managed tunnel.
func externalSSHForward(t *testing.T, remote, kind string) (string, func()) {
	t.Helper()
	ssh, config := externalSSHConfiguration(t)
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	_ = listener.Close()
	endpoint := "tcp://" + address
	if kind == "unix" {
		directory, err := os.MkdirTemp("/tmp", "lzug-external-")
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = os.RemoveAll(directory) })
		address = filepath.Join(directory, "admin.sock")
		endpoint = "unix://" + address
	}
	ctx, cancel := context.WithCancel(context.Background())
	command := exec.CommandContext(ctx, ssh, "-F", config, "-N", "-T", "-n",
		"-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
		"-o", "ExitOnForwardFailure=yes", "-L", address+":"+remote, "test-host")
	command.WaitDelay = time.Second
	var logs bytes.Buffer
	command.Stderr = &logs
	if err := command.Start(); err != nil {
		cancel()
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() { _ = command.Wait(); close(done) }()
	stop := func() { cancel(); <-done }
	t.Cleanup(stop)
	network, address, err := parseEndpoint(endpoint)
	if err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for {
		select {
		case <-done:
			t.Fatal("external SSH fixture failed:", logs.String())
		default:
		}
		connection, err := net.DialTimeout(network, address, 50*time.Millisecond)
		if err == nil {
			_ = connection.Close()
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("external SSH fixture did not become ready")
		}
		time.Sleep(10 * time.Millisecond)
	}
	return endpoint, stop
}

func TestExternalSSHArtifactsLive(t *testing.T) {
	path := os.Getenv("LZUG_SOCKET_ARTIFACT_TEST_PATH")
	if path == "" {
		t.Skip("run through backend.tests.test_admin_socket_artifacts")
	}
	for _, kind := range []string{"unix", "tcp"} {
		t.Run(kind, func(t *testing.T) {
			endpoint, stop := externalSSHForward(t, path, kind)
			transport := &SocketTransport{Endpoint: endpoint}
			testLiveArtifactRoundtrip(t, transport)
			// The CLI must leave its externally owned listener available.
			network, address, _ := parseEndpoint(endpoint)
			connection, err := net.DialTimeout(network, address, time.Second)
			if err != nil {
				t.Fatal("CLI removed the external endpoint")
			}
			_ = connection.Close()
			stop()
			_, _, err = transport.Execute(context.Background(), BackendRequest{Version: 1, Command: "config", Arguments: map[string]any{}})
			failure := runtimeFailure(err)
			if failure.Class != "connection_failed" || unknownOutcome(failure) {
				t.Fatalf("lost external endpoint diagnosis: %#v", failure)
			}
		})
	}
}
