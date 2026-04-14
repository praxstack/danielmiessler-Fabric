package pipeline

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

const (
	cleanupRunDirEnv   = "FABRIC_PIPELINE_CLEANUP_RUN_DIR"
	cleanupDelayMsEnv  = "FABRIC_PIPELINE_CLEANUP_DELAY_MS"
	defaultCleanupWait = 5 * time.Second
)

type RunState struct {
	RunID       string     `json:"run_id"`
	Status      string     `json:"status"`
	PID         int        `json:"pid"`
	StartedAt   time.Time  `json:"started_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
	Pipeline    string     `json:"pipeline"`
	RunDir      string     `json:"run_dir"`
	SourceMode  SourceMode `json:"source_mode"`
}

// CleanupRunDirFromEnv checks the FABRIC_PIPELINE_CLEANUP_RUN_DIR environment variable and, if set,
// waits for a configured delay and then deletes that run directory.
// If FABRIC_PIPELINE_CLEANUP_DELAY_MS is set it is parsed as a number of milliseconds; parse failures
// are returned as an error. The boolean return is true when a cleanup was attempted (whether it
// succeeded or failed) and false when no cleanup was requested because the environment variable was
// not set.
func CleanupRunDirFromEnv() (bool, error) {
	runDir := os.Getenv(cleanupRunDirEnv)
	if runDir == "" {
		return false, nil
	}

	delay := defaultCleanupWait
	if rawDelay := os.Getenv(cleanupDelayMsEnv); rawDelay != "" {
		var millis int
		if _, err := fmt.Sscanf(rawDelay, "%d", &millis); err != nil {
			return true, fmt.Errorf("parse %s: %w", cleanupDelayMsEnv, err)
		}
		delay = time.Duration(millis) * time.Millisecond
	}

	time.Sleep(delay)
	if err := deleteRunDir(runDir); err != nil {
		return true, err
	}
	return true, nil
}

// startCleanupHelper starts a helper process of the current executable that will remove the specified run directory after the given delay.
// The child process is invoked with environment variables `FABRIC_PIPELINE_CLEANUP_RUN_DIR` set to runDir and
// `FABRIC_PIPELINE_CLEANUP_DELAY_MS` set to delay in milliseconds.
// runDir is the filesystem path to delete; delay is the wait duration before deletion is attempted.
// It returns an error if the current executable cannot be resolved or if the helper process cannot be started.
func startCleanupHelper(runDir string, delay time.Duration) error {
	executable, err := os.Executable()
	if err != nil {
		return fmt.Errorf("resolve current executable for cleanup helper: %w", err)
	}

	cmd := exec.Command(executable)
	cmd.Env = append(os.Environ(),
		cleanupRunDirEnv+"="+runDir,
		cleanupDelayMsEnv+"="+fmt.Sprintf("%d", delay.Milliseconds()),
	)
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start cleanup helper: %w", err)
	}
	return nil
}

// cleanupExpiredRuns scans the runRoot directory for per-run subdirectories, loads each
// subdirectory's run.json, and deletes any run directory whose RunState.ExpiresAt is set
// and is not after the provided now time. If the runRoot becomes empty it attempts to
// remove it. It returns any error encountered while stat-ing, reading, deleting, or
// removing the root.
func cleanupExpiredRuns(runRoot string, now time.Time) error {
	info, err := os.Stat(runRoot)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("stat run root %s: %w", runRoot, err)
	}
	if !info.IsDir() {
		return fmt.Errorf("run root %s is not a directory", runRoot)
	}

	entries, err := os.ReadDir(runRoot)
	if err != nil {
		return fmt.Errorf("read run root %s: %w", runRoot, err)
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		runDir := filepath.Join(runRoot, entry.Name())
		state, err := readRunState(filepath.Join(runDir, "run.json"))
		if err != nil {
			continue
		}
		if state.ExpiresAt != nil && !state.ExpiresAt.After(now) {
			if err := deleteRunDir(runDir); err != nil {
				return err
			}
		}
	}

	return removeRunRootIfEmpty(runRoot)
}

// readRunState reads and parses a JSON-encoded RunState from the provided file path.
// It returns the parsed RunState or an error if the file cannot be read or the JSON is invalid.
func readRunState(path string) (*RunState, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var state RunState
	if err := json.Unmarshal(content, &state); err != nil {
		return nil, err
	}
	return &state, nil
}

// deleteRunDir removes the specified run directory and then attempts to remove its parent run root if that root becomes empty.
// It returns an error if removing the run directory fails or if removing the parent run root fails for reasons other than it not existing.
func deleteRunDir(runDir string) error {
	if err := os.RemoveAll(runDir); err != nil {
		return fmt.Errorf("remove run dir %s: %w", runDir, err)
	}
	return removeRunRootIfEmpty(filepath.Dir(runDir))
}

// removeRunRootIfEmpty removes the directory at runRoot when it exists and contains no entries.
// If the directory does not exist or is not empty, it does nothing and returns nil.
// Returns an error only if the directory exists and removal fails.
func removeRunRootIfEmpty(runRoot string) error {
	entries, err := os.ReadDir(runRoot)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("read run root %s: %w", runRoot, err)
	}
	if len(entries) > 0 {
		return nil
	}
	if err := os.Remove(runRoot); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("remove empty run root %s: %w", runRoot, err)
	}
	return nil
}
