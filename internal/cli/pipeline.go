package cli

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/danielmiessler/fabric/internal/core"
	"github.com/danielmiessler/fabric/internal/i18n"
	"github.com/danielmiessler/fabric/internal/pipeline"
)

var pipelineRunOptions = func(invocationDir string) pipeline.RunOptions {
	return pipeline.RunOptions{InvocationDir: invocationDir}
}

// handlePipelineCommands inspects pipeline-related CLI flags and, if any are present,
// performs validation of flag combinations, loads and preflights the specified pipeline,
// resolves the pipeline source, optionally emits a dry-run plan, runs the pipeline, and
// writes the pipeline's final output to a file when requested.
//
// The currentFlags parameter supplies parsed CLI flag values; registry supplies plugins
// and services used for preflight, scraping, and execution. The function returns
// (handled=true, err) when it processed pipeline-related flags (successful or with error),
// and (handled=false, nil) when no pipeline-related flags were provided.
func handlePipelineCommands(currentFlags *Flags, registry *core.PluginRegistry) (handled bool, err error) {
	if currentFlags.ValidatePipeline == "" && currentFlags.Pipeline == "" {
		if hasPipelineExecutionFlags(currentFlags) {
			return true, fmt.Errorf("--from-stage, --to-stage, --only-stage, --pipeline-events-json, and --validate-only require --pipeline")
		}
		return false, nil
	}

	if currentFlags.ValidatePipeline != "" && currentFlags.Pipeline != "" {
		return true, fmt.Errorf("--validate-pipeline and --pipeline cannot be used together")
	}
	if currentFlags.ValidatePipeline != "" && currentFlags.ValidateOnly {
		return true, fmt.Errorf("--validate-only requires --pipeline and cannot be used with --validate-pipeline")
	}

	loader, err := pipeline.NewDefaultLoader()
	if err != nil {
		return true, err
	}

	if currentFlags.ValidatePipeline != "" {
		if hasPipelineRuntimeOnlyFlags(currentFlags) || currentFlags.DryRun {
			return true, fmt.Errorf("--validate-pipeline cannot be combined with runtime pipeline flags")
		}
		var pipe *pipeline.Pipeline
		if pipe, err = loader.LoadFilePath(currentFlags.ValidatePipeline); err != nil {
			return true, err
		}
		if err = pipeline.Preflight(context.Background(), pipe, pipeline.PreflightOptions{Registry: registry}); err != nil {
			return true, err
		}
		fmt.Printf("pipeline valid: %s\n", pipe.Name)
		return true, nil
	}

	if currentFlags.Pattern != "" || currentFlags.Context != "" || currentFlags.Session != "" || len(currentFlags.Attachments) > 0 || currentFlags.argumentMessage != "" {
		return true, fmt.Errorf("--pipeline cannot be combined with pattern/chat-style inputs")
	}

	var pipe *pipeline.Pipeline
	if pipe, err = loader.LoadNamed(currentFlags.Pipeline); err != nil {
		return true, err
	}
	if err = pipeline.Preflight(context.Background(), pipe, pipeline.PreflightOptions{Registry: registry}); err != nil {
		return true, err
	}

	if currentFlags.ValidateOnly {
		if hasPipelineRuntimeOnlyFlags(currentFlags) || currentFlags.DryRun {
			return true, fmt.Errorf("--validate-only cannot be combined with runtime pipeline flags")
		}
		fmt.Printf("pipeline valid: %s\n", pipe.Name)
		return true, nil
	}

	var source pipeline.RunSource
	if source, err = resolvePipelineSource(currentFlags, registry); err != nil {
		return true, err
	}

	invocationDir, err := os.Getwd()
	if err != nil {
		return true, fmt.Errorf("determine current working directory: %w", err)
	}

	runOptions := pipelineRunOptions(invocationDir)
	runOptions.FromStage = currentFlags.FromStage
	runOptions.ToStage = currentFlags.ToStage
	runOptions.OnlyStage = currentFlags.OnlyStage
	runOptions.JSONEvents = currentFlags.PipelineEventsJSON

	if currentFlags.DryRun {
		if err := emitPipelineDryRunPlan(pipe, source, runOptions); err != nil {
			return true, err
		}
		return true, nil
	}

	runner := pipeline.NewRunner(os.Stdout, os.Stderr, registry)
	result, err := runner.Run(context.Background(), pipe, source, runOptions)
	if currentFlags.Output != "" && result != nil && result.FinalOutput != "" {
		if outputErr := CreateOutputFile(result.FinalOutput, currentFlags.Output); outputErr != nil {
			if err != nil {
				return true, fmt.Errorf("%w; output file error: %w", err, outputErr)
			}
			return true, outputErr
		}
	}
	if err != nil {
		return true, err
	}

	return true, nil
}

// hasPipelineExecutionFlags reports whether any CLI flags that modify pipeline execution are set.
// It returns true if any of ValidateOnly, FromStage, ToStage, OnlyStage, or PipelineEventsJSON are enabled.
func hasPipelineExecutionFlags(currentFlags *Flags) bool {
	return currentFlags.ValidateOnly || currentFlags.FromStage != "" || currentFlags.ToStage != "" || currentFlags.OnlyStage != "" || currentFlags.PipelineEventsJSON
}

// hasPipelineRuntimeOnlyFlags reports whether any runtime-only pipeline flags are set.
// It reports true when FromStage, ToStage, OnlyStage, or PipelineEventsJSON is provided.
func hasPipelineRuntimeOnlyFlags(currentFlags *Flags) bool {
	return currentFlags.FromStage != "" || currentFlags.ToStage != "" || currentFlags.OnlyStage != "" || currentFlags.PipelineEventsJSON
}

type pipelineDryRunPlan struct {
	Pipeline         string                `json:"pipeline"`
	PipelineFile     string                `json:"pipeline_file"`
	Source           pipeline.RunSource    `json:"source"`
	SelectedStageIDs []string              `json:"selected_stage_ids"`
	SkippedStageIDs  []string              `json:"skipped_stage_ids,omitempty"`
	Stages           []pipelineDryRunStage `json:"stages"`
}

type pipelineDryRunStage struct {
	Index       int    `json:"index"`
	ID          string `json:"id"`
	Executor    string `json:"executor"`
	Role        string `json:"role,omitempty"`
	FinalOutput bool   `json:"final_output"`
	Selected    bool   `json:"selected"`
}

// emitPipelineDryRunPlan builds and prints an indented JSON dry-run plan for the given pipeline,
// describing which stages would be selected or skipped and per-stage metadata.
//
// The produced plan includes pipeline name and file, the resolved source, lists of selected and
// skipped stage IDs, and an array of stage descriptors (index, id, executor, resolved role,
// final_output flag, and whether the stage is selected). The plan is written to standard output.
//
// It returns any error encountered while selecting stages or marshaling the plan to JSON.
func emitPipelineDryRunPlan(pipe *pipeline.Pipeline, source pipeline.RunSource, opts pipeline.RunOptions) error {
	selectedIndices, selectedSet, err := pipeline.SelectStageIndices(pipe.Stages, opts.FromStage, opts.ToStage, opts.OnlyStage)
	if err != nil {
		return err
	}

	selectedIDs := make([]string, 0, len(selectedIndices))
	skippedIDs := make([]string, 0, len(pipe.Stages))
	stages := make([]pipelineDryRunStage, 0, len(pipe.Stages))
	for index, stage := range pipe.Stages {
		_, selected := selectedSet[index]
		if selected {
			selectedIDs = append(selectedIDs, stage.ID)
		} else {
			skippedIDs = append(skippedIDs, stage.ID)
		}
		stages = append(stages, pipelineDryRunStage{
			Index:       index,
			ID:          stage.ID,
			Executor:    string(stage.Executor),
			Role:        string(dryRunEffectiveStageRole(stage)),
			FinalOutput: stage.FinalOutput,
			Selected:    selected,
		})
	}

	plan := pipelineDryRunPlan{
		Pipeline:         pipe.Name,
		PipelineFile:     pipe.FilePath,
		Source:           source,
		SelectedStageIDs: selectedIDs,
		SkippedStageIDs:  skippedIDs,
		Stages:           stages,
	}
	encoded, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(encoded))
	return nil
}

// dryRunEffectiveStageRole returns the effective role for a stage during a dry-run.
//
// If the stage's Role is explicitly set (not StageRoleDefault), that role is returned.
// For builtin executors with known builtin names, specific roles are mapped:
// "validate_declared_outputs" -> StageRoleValidate and
// "write_publish_manifest" -> StageRolePublish.
// In all other cases StageRoleDefault is returned.
func dryRunEffectiveStageRole(stage pipeline.Stage) pipeline.StageRole {
	if stage.Role != pipeline.StageRoleDefault {
		return stage.Role
	}
	if stage.Executor == pipeline.ExecutorBuiltin && stage.Builtin != nil {
		switch stage.Builtin.Name {
		case "validate_declared_outputs":
			return pipeline.StageRoleValidate
		case "write_publish_manifest":
			return pipeline.StageRolePublish
		}
	}
	return pipeline.StageRoleDefault
}

// resolvePipelineSource resolves and validates a single pipeline source provided via stdin, a filesystem path (--source),
// or a scrape URL (--scrape_url) and returns a pipeline.RunSource describing the chosen source.
//
// Exactly one of currentFlags.stdinProvided, currentFlags.Source, or currentFlags.ScrapeURL must be set; otherwise an error is returned.
// If stdin is provided, the returned RunSource has Mode SourceModeStdin and Payload set to currentFlags.stdinMessage.
// If ScrapeURL is provided, the registry must have Jina configured; the URL is fetched and the returned RunSource has
// Mode SourceModeScrapeURL, Reference set to the URL, and Payload to the scraped content. If registry is not configured or
// scraping fails, an error is returned.
// If Source is provided as a path, the path is resolved to an absolute path. If the path is a directory, the returned RunSource
// has Mode SourceModeSource with Reference and Payload set to the absolute directory path. If the path is a file, the file is
// read and the returned RunSource has Mode SourceModeSource, Reference set to the absolute file path, and Payload set to the
// file contents. Errors are returned for path resolution, stat, or read failures.
func resolvePipelineSource(currentFlags *Flags, registry *core.PluginRegistry) (pipeline.RunSource, error) {
	sourceCount := 0
	if currentFlags.stdinProvided {
		sourceCount++
	}
	if currentFlags.Source != "" {
		sourceCount++
	}
	if currentFlags.ScrapeURL != "" {
		sourceCount++
	}

	if sourceCount != 1 {
		return pipeline.RunSource{}, fmt.Errorf("--pipeline requires exactly one source: stdin, --source, or --scrape_url")
	}

	if currentFlags.stdinProvided {
		return pipeline.RunSource{
			Mode:    pipeline.SourceModeStdin,
			Payload: currentFlags.stdinMessage,
		}, nil
	}

	if currentFlags.ScrapeURL != "" {
		if registry == nil || registry.Jina == nil || !registry.Jina.IsConfigured() {
			return pipeline.RunSource{}, fmt.Errorf("%s", i18n.T("scraping_not_configured"))
		}
		scrapedContent, err := registry.Jina.ScrapeURL(currentFlags.ScrapeURL)
		if err != nil {
			return pipeline.RunSource{}, err
		}
		return pipeline.RunSource{
			Mode:      pipeline.SourceModeScrapeURL,
			Reference: currentFlags.ScrapeURL,
			Payload:   scrapedContent,
		}, nil
	}

	absPath, err := filepath.Abs(currentFlags.Source)
	if err != nil {
		return pipeline.RunSource{}, fmt.Errorf("resolve source path %s: %w", currentFlags.Source, err)
	}

	info, err := os.Stat(absPath)
	if err != nil {
		return pipeline.RunSource{}, fmt.Errorf("stat source path %s: %w", absPath, err)
	}

	if info.IsDir() {
		return pipeline.RunSource{
			Mode:      pipeline.SourceModeSource,
			Reference: absPath,
			Payload:   absPath,
		}, nil
	}

	content, err := os.ReadFile(absPath)
	if err != nil {
		return pipeline.RunSource{}, fmt.Errorf("read source file %s: %w", absPath, err)
	}

	return pipeline.RunSource{
		Mode:      pipeline.SourceModeSource,
		Reference: absPath,
		Payload:   string(content),
	}, nil
}
