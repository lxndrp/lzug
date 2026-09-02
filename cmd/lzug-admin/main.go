package main

//go:generate go run ../lzug-admin-reference --write ../../docs/developers/reference/cli.md

import (
	"context"
	"fmt"
	"os"
	"os/signal"

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
	var ctx context.Context = context.Background()
	stop := func() {}
	if !admincli.InteractiveRequested(os.Args[1:]) {
		ctx, stop = signal.NotifyContext(ctx, os.Interrupt)
	}
	defer stop()
	application := admincli.NewApplication(
		registry,
		admincli.BuildInfo{
			Version:  applicationVersion,
			Revision: applicationRevision,
			Tag:      applicationTag,
		},
		admincli.NewContainerRuntimeFactory(),
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
