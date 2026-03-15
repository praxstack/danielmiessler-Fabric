package pipeline

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/danielmiessler/fabric/internal/core"
	"github.com/danielmiessler/fabric/internal/plugins/strategy"
)

var envReferencePattern = regexp.MustCompile(`\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)`)
var templateTokenPattern = regexp.MustCompile(`\{\{([^{}]+)\}\}`)

type PreflightOptions struct {
	Registry              *core.PluginRegistry
	SkipPatternValidation func(Stage) bool
}

// Preflight validates a Pipeline and performs preparatory checks and expansions for each Stage.
// It expands environment variable references in stage fields (pattern, context, strategy, variables, artifacts),
// performs executor-specific validations (builtin support, command program and cwd resolution, or pattern loading and variable validation),
// and consults the provided PreflightOptions (e.g., Registry and SkipPatternValidation) when validating fabric pattern stages.
// It returns an error describing the pipeline and stage context if validation, expansion, or resource resolution fails.
func Preflight(ctx context.Context, p *Pipeline, opts PreflightOptions) error {
	if err := Validate(p); err != nil {
		return err
	}
	if ctx != nil {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
	}

	for i := range p.Stages {
		stage := &p.Stages[i]

		var err error
		stage.Pattern, err = expandEnvReferences(stage.Pattern)
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q pattern: %w", p.Name, stage.ID, err)
		}
		stage.Context, err = expandEnvReferences(stage.Context)
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q context: %w", p.Name, stage.ID, err)
		}
		stage.Strategy, err = expandEnvReferences(stage.Strategy)
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q strategy: %w", p.Name, stage.ID, err)
		}
		for key, value := range stage.Variables {
			stage.Variables[key], err = expandEnvReferences(value)
			if err != nil {
				return fmt.Errorf("pipeline %q stage %q variable %q: %w", p.Name, stage.ID, key, err)
			}
		}
		for artifactIndex := range stage.Artifacts {
			stage.Artifacts[artifactIndex].Path, err = expandEnvReferences(stage.Artifacts[artifactIndex].Path)
			if err != nil {
				return fmt.Errorf("pipeline %q stage %q artifact %q: %w", p.Name, stage.ID, stage.Artifacts[artifactIndex].Name, err)
			}
		}

		switch stage.Executor {
		case ExecutorBuiltin:
			if !isSupportedBuiltin(stage.Builtin.Name) {
				return fmt.Errorf("pipeline %q stage %q builtin %q is not supported", p.Name, stage.ID, stage.Builtin.Name)
			}
		case ExecutorCommand:
			if err := preflightCommandStage(p, stage); err != nil {
				return err
			}
		case ExecutorFabricPattern:
			if opts.SkipPatternValidation != nil && opts.SkipPatternValidation(*stage) {
				continue
			}
			if err := preflightPatternStage(p, stage, opts.Registry); err != nil {
				return err
			}
		}
	}

	return nil
}

// preflightCommandStage validates and prepares a command-style stage by expanding environment references,
// resolving the command program path when possible, and validating the working directory.
//
// It expands environment variables in Command.Program, Command.Cwd, Command.Args, and Command.Env,
// updates the stage in-place, and resolves Command.Program to an absolute path unless it contains a runtime
// placeholder. If Command.Cwd is provided and does not contain a runtime placeholder, it is resolved
// relative to the pipeline file (when applicable) and verified to exist and be a directory. On failure
// it returns an error that includes the pipeline name and stage ID.
func preflightCommandStage(p *Pipeline, stage *Stage) error {
	var err error
	stage.Command.Program, err = expandEnvReferences(stage.Command.Program)
	if err != nil {
		return fmt.Errorf("pipeline %q stage %q command.program: %w", p.Name, stage.ID, err)
	}
	stage.Command.Cwd, err = expandEnvReferences(stage.Command.Cwd)
	if err != nil {
		return fmt.Errorf("pipeline %q stage %q command.cwd: %w", p.Name, stage.ID, err)
	}
	for i := range stage.Command.Args {
		stage.Command.Args[i], err = expandEnvReferences(stage.Command.Args[i])
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q command.args[%d]: %w", p.Name, stage.ID, i, err)
		}
	}
	for key, value := range stage.Command.Env {
		stage.Command.Env[key], err = expandEnvReferences(value)
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q command.env.%s: %w", p.Name, stage.ID, key, err)
		}
	}

	if !containsRuntimePlaceholder(stage.Command.Program) {
		if resolvedProgram, err := resolveCommandProgram(p, stage.Command.Program); err != nil {
			return fmt.Errorf("pipeline %q stage %q command.program: %w", p.Name, stage.ID, err)
		} else {
			stage.Command.Program = resolvedProgram
		}
	}
	if stage.Command.Cwd != "" && !containsRuntimePlaceholder(stage.Command.Cwd) {
		resolvedCwd := resolvePipelinePath(p, stage.Command.Cwd)
		info, err := os.Stat(resolvedCwd)
		if err != nil {
			return fmt.Errorf("pipeline %q stage %q command.cwd: %w", p.Name, stage.ID, err)
		}
		if !info.IsDir() {
			return fmt.Errorf("pipeline %q stage %q command.cwd %q is not a directory", p.Name, stage.ID, resolvedCwd)
		}
		stage.Command.Cwd = resolvedCwd
	}

	return nil
}

// preflightPatternStage validates a fabric pattern stage using the provided plugin registry.
// It requires a non-nil registry and resolves pattern and context paths that look relative
// against the pipeline file path. It loads the raw pattern content and ensures all required
// template variables are supplied by the stage. If the stage declares a context or strategy,
// their existence and availability are verified. Returns nil on success or an error describing
// the pipeline, stage and offending field when validation fails.
func preflightPatternStage(p *Pipeline, stage *Stage, registry *core.PluginRegistry) error {
	if registry == nil {
		return fmt.Errorf("pipeline %q stage %q cannot validate patterns without plugin registry", p.Name, stage.ID)
	}
	if looksLikeRelativePath(stage.Pattern) {
		stage.Pattern = resolvePipelinePath(p, stage.Pattern)
	}
	if looksLikeRelativePath(stage.Context) {
		stage.Context = resolvePipelinePath(p, stage.Context)
	}
	patternContent, err := loadRawPatternContent(stage.Pattern, registry)
	if err != nil {
		return fmt.Errorf("pipeline %q stage %q pattern %q: %w", p.Name, stage.ID, stage.Pattern, err)
	}
	if err := validatePatternVariables(patternContent, stage.Variables); err != nil {
		return fmt.Errorf("pipeline %q stage %q pattern %q: %w", p.Name, stage.ID, stage.Pattern, err)
	}
	if stage.Context != "" {
		if _, err := registry.Db.Contexts.Get(stage.Context); err != nil {
			return fmt.Errorf("pipeline %q stage %q context %q: %w", p.Name, stage.ID, stage.Context, err)
		}
	}
	if stage.Strategy != "" {
		if _, err := strategy.LoadStrategy(stage.Strategy); err != nil {
			return fmt.Errorf("pipeline %q stage %q strategy %q: %w", p.Name, stage.ID, stage.Strategy, err)
		}
	}
	return nil
}

// loadRawPatternContent loads raw pattern content for the given source.
// If source is an absolute path or looks like a relative path, it reads and returns the file contents.
// Otherwise it retrieves the raw pattern named by source from registry.Db.Patterns and returns its Pattern field.
// Returns an error if file reading or registry retrieval fails.
func loadRawPatternContent(source string, registry *core.PluginRegistry) (string, error) {
	if filepath.IsAbs(source) || looksLikeRelativePath(source) {
		content, err := os.ReadFile(source)
		if err != nil {
			return "", err
		}
		return string(content), nil
	}

	pattern, err := registry.Db.Patterns.GetRaw(source)
	if err != nil {
		return "", err
	}
	return pattern.Pattern, nil
}

// validatePatternVariables verifies that every template token found in patternContent
// (except empty tokens, the token "input", and tokens prefixed with "plugin:" or "ext:")
// has a corresponding entry in variables.
//
// It returns an error "missing required variable: <name>" for the first token that is
// not present in variables; otherwise it returns nil.
func validatePatternVariables(patternContent string, variables map[string]string) error {
	matches := templateTokenPattern.FindAllStringSubmatch(patternContent, -1)
	for _, match := range matches {
		raw := strings.TrimSpace(match[1])
		if raw == "" || raw == "input" {
			continue
		}
		if strings.HasPrefix(raw, "plugin:") || strings.HasPrefix(raw, "ext:") {
			continue
		}
		if _, ok := variables[raw]; !ok {
			return fmt.Errorf("missing required variable: %s", raw)
		}
	}
	return nil
}

// expandEnvReferences expands environment variable references in the provided string.
// It returns the input with all ${VAR} or $VAR references replaced by their environment values.
// If the input is empty it is returned unchanged. If any referenced environment variable is not
// set, an error identifying the missing variable is returned.
func expandEnvReferences(value string) (string, error) {
	if value == "" {
		return value, nil
	}
	matches := envReferencePattern.FindAllStringSubmatch(value, -1)
	for _, match := range matches {
		name := match[1]
		if name == "" {
			name = match[2]
		}
		if _, exists := os.LookupEnv(name); !exists {
			return "", fmt.Errorf("missing environment variable %q", name)
		}
	}
	return os.ExpandEnv(value), nil
}

// resolveCommandProgram resolves a command identifier to an executable filesystem path.
// If `program` is empty it returns an empty string.
// If `program` is an absolute path it verifies the file exists and returns it.
// If `program` looks like a relative path it resolves the path relative to the pipeline file and verifies the file exists.
// Otherwise it searches for the executable in `PATH` and returns the located path.
// An error is returned if the file does not exist or the lookup fails.
func resolveCommandProgram(p *Pipeline, program string) (string, error) {
	if program == "" {
		return "", nil
	}
	if filepath.IsAbs(program) {
		if _, err := os.Stat(program); err != nil {
			return "", err
		}
		return program, nil
	}
	if looksLikeRelativePath(program) {
		resolved := resolvePipelinePath(p, program)
		if _, err := os.Stat(resolved); err != nil {
			return "", err
		}
		return resolved, nil
	}
	resolved, err := exec.LookPath(program)
	if err != nil {
		return "", err
	}
	return resolved, nil
}

// resolvePipelinePath returns value unchanged if value is empty, is an absolute path,
// or the pipeline has no FilePath; otherwise it interprets value as relative to the
// pipeline file directory, joins it with that directory, and returns the cleaned path.
func resolvePipelinePath(p *Pipeline, value string) string {
	if value == "" || filepath.IsAbs(value) || p.FilePath == "" {
		return value
	}
	return filepath.Clean(filepath.Join(filepath.Dir(p.FilePath), value))
}

// looksLikeRelativePath reports whether the provided path string appears to be a relative path.
// It returns true if the string starts with "." or contains a path separator, false otherwise.
func looksLikeRelativePath(value string) bool {
	return strings.HasPrefix(value, ".") || strings.ContainsRune(value, filepath.Separator)
}

// containsRuntimePlaceholder reports whether the input string contains a runtime placeholder pattern.
// It returns `true` if the string matches the runtime placeholder regular expression, `false` otherwise.
func containsRuntimePlaceholder(value string) bool {
	return runtimePlaceholderPattern.MatchString(value)
}

// isSupportedBuiltin reports whether the given builtin executor name is supported.
// It returns true for "passthrough", "noop", "source_capture", "validate_declared_outputs",
// and "write_publish_manifest", and false otherwise.
func isSupportedBuiltin(name string) bool {
	switch name {
	case "passthrough", "noop", "source_capture", "validate_declared_outputs", "write_publish_manifest":
		return true
	default:
		return false
	}
}
