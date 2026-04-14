package main

import (
	"fmt"
	"os"

	"github.com/jessevdk/go-flags"

	"github.com/danielmiessler/fabric/internal/cli"
	"github.com/danielmiessler/fabric/internal/pipeline"
)

// main is the program entry point.
// It calls pipeline.CleanupRunDirFromEnv(); if that call reports it handled the request,
// main prints any returned error to stderr and exits with status 1, otherwise it returns
// immediately to skip CLI startup. If not handled, main invokes cli.Cli(version) and,
// for errors that are not help output, prints the error to stderr and exits with status 1.
func main() {
	if handled, err := pipeline.CleanupRunDirFromEnv(); handled {
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s\n", err)
			os.Exit(1)
		}
		return
	}

	err := cli.Cli(version)
	if err != nil && !flags.WroteHelp(err) {
		fmt.Fprintf(os.Stderr, "%s\n", err)
		os.Exit(1)
	}
}
