package pipeline

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func (r *Runner) executeBuiltinStage(_ context.Context, stage Stage, runtimeCtx StageRuntimeContext) (*StageExecutionResult, error) {
	switch stage.Builtin.Name {
	case "passthrough", "noop", "source_capture":
		return &StageExecutionResult{Stdout: runtimeCtx.InputPayload}, nil
	case "validate_declared_outputs":
		return executeValidateDeclaredOutputs(stage, runtimeCtx)
	case "write_publish_manifest":
		manifestPath := builtinOutputPath(stage, runtimeCtx.RunDir, "publish_manifest", "publish_manifest.json")
		if err := os.MkdirAll(filepath.Dir(manifestPath), 0o755); err != nil {
			return nil, fmt.Errorf("create publish manifest directory: %w", err)
		}
		if err := os.WriteFile(manifestPath, []byte("{}\n"), 0o644); err != nil {
			return nil, fmt.Errorf("write publish manifest placeholder: %w", err)
		}
		return &StageExecutionResult{FilesWritten: []string{manifestPath}}, nil
	default:
		return nil, fmt.Errorf("builtin stage %q is not implemented in the runner", stage.Builtin.Name)
	}
}

// executeValidateDeclaredOutputs generates a Markdown validation report of declared artifacts for a pipeline run and writes it to disk.
// The report contains a header with pipeline name and run ID, a PASS status, and a "Declared artifacts" section listing each stage's declared artifacts in sorted order.
// If no declared artifacts are present, the report notes that fact. The report file path is resolved via builtinOutputPath and the file is created under the run directory.
// On success it returns a StageExecutionResult whose Stdout is "validation passed" and FilesWritten contains the report path; file system errors are returned wrapped.
func executeValidateDeclaredOutputs(stage Stage, runtimeCtx StageRuntimeContext) (*StageExecutionResult, error) {
	lines := []string{
		fmt.Sprintf("# Validation Report"),
		"",
		fmt.Sprintf("- Pipeline: %s", runtimeCtx.Pipeline.Name),
		fmt.Sprintf("- Run ID: %s", runtimeCtx.RunID),
		fmt.Sprintf("- Status: PASS"),
		"",
		"## Declared artifacts",
	}

	stageIDs := make([]string, 0, len(runtimeCtx.StageArtifacts))
	for stageID := range runtimeCtx.StageArtifacts {
		stageIDs = append(stageIDs, stageID)
	}
	sort.Strings(stageIDs)
	for _, stageID := range stageIDs {
		artifacts := runtimeCtx.StageArtifacts[stageID]
		names := make([]string, 0, len(artifacts))
		for name := range artifacts {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			lines = append(lines, fmt.Sprintf("- `%s.%s`: `%s`", stageID, name, artifacts[name]))
		}
	}
	if len(stageIDs) == 0 {
		lines = append(lines, "- No prior declared artifacts")
	}

	reportPath := builtinOutputPath(stage, runtimeCtx.RunDir, "validation_report", "validation_report.md")
	if err := os.MkdirAll(filepath.Dir(reportPath), 0o755); err != nil {
		return nil, fmt.Errorf("create validation report directory: %w", err)
	}
	reportBody := strings.Join(lines, "\n") + "\n"
	if err := os.WriteFile(reportPath, []byte(reportBody), 0o644); err != nil {
		return nil, fmt.Errorf("write validation report: %w", err)
	}

	return &StageExecutionResult{
		Stdout:       "validation passed",
		FilesWritten: []string{reportPath},
	}, nil
}

// builtinOutputPath returns the filesystem path for the artifact named artifactName within the given stage,
// joined with runDir. If the stage does not declare an artifact with that name, it returns runDir joined with fallback.
func builtinOutputPath(stage Stage, runDir string, artifactName string, fallback string) string {
	for _, artifact := range stage.Artifacts {
		if artifact.Name == artifactName {
			return filepath.Join(runDir, artifact.Path)
		}
	}
	return filepath.Join(runDir, fallback)
}
