package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"

	"github.com/lxndrp/lzug/operator-cli/internal/admincli"
)

func main() {
	writePath := flag.String("write", "", "write the generated CLI reference to this path")
	checkPath := flag.String("check", "", "verify that this CLI reference is current")
	flag.Parse()
	if (*writePath == "") == (*checkPath == "") || flag.NArg() != 0 {
		_, _ = fmt.Fprintln(os.Stderr, "exactly one of --write or --check is required")
		os.Exit(2)
	}
	registry, err := admincli.DefaultRegistry()
	if err != nil {
		_, _ = fmt.Fprintln(os.Stderr, "command registry is invalid")
		os.Exit(1)
	}
	generated := []byte(admincli.GenerateReference(registry))
	if *writePath != "" {
		if err := os.WriteFile(*writePath, generated, 0o644); err != nil {
			_, _ = fmt.Fprintln(os.Stderr, "CLI reference could not be written")
			os.Exit(1)
		}
		return
	}
	current, err := os.ReadFile(*checkPath)
	if err != nil || !bytes.Equal(current, generated) {
		_, _ = fmt.Fprintln(os.Stderr, "CLI reference is stale; run go generate ./cmd/lzug-admin")
		os.Exit(1)
	}
}
