package main

//go:generate go run ../../internal/tools/cli-reference --write ../../../docs/developers/reference/cli.md

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/lxndrp/lzug/operator-cli/internal/admincli"
)

var applicationVersion = "development"
var applicationRevision = "unknown"
var applicationTag = ""

func main() {
	registry, err := admincli.DefaultRegistry()
	if err != nil {
		_, _ = fmt.Fprintln(os.Stderr, "Error [unexpected_local_error]: The command registry is invalid.")
		os.Exit(admincli.ExitUnexpected)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM)
	defer stop()
	if !admincli.InteractiveRequested(os.Args[1:]) {
		var stopInterrupt context.CancelFunc
		ctx, stopInterrupt = signal.NotifyContext(ctx, os.Interrupt)
		defer stopInterrupt()
	}
	application := admincli.NewApplication(
		registry,
		admincli.BuildInfo{
			Version:  applicationVersion,
			Revision: applicationRevision,
			Tag:      applicationTag,
		},
		admincli.NewTargetRuntimeFactory(),
		admincli.NewSystemConfigResolver(),
		admincli.NewConsoleInput(os.Stdin, os.Stderr),
		admincli.NewOutputRenderer(
			os.Stdout,
			os.Stderr,
		),
	)
	if code := application.Run(ctx, os.Args[1:]); code != admincli.ExitOK {
		os.Exit(code)
	}
}

func versionText() string {
	return admincli.VersionText(admincli.BuildInfo{Version: applicationVersion})
}

func cliBuildMetadata() any {
	return admincli.BuildMetadata(admincli.BuildInfo{
		Version:  applicationVersion,
		Revision: applicationRevision,
		Tag:      applicationTag,
	})
}
