# Pipeline Implementation Verification Report

**Date:** 2026-03-15  
**Branch:** `feat/fabric-executable-pipelines` (16 commits)  
**Verified against:** `docs/spec.md`, `docs/prd.md`, `docs/plans/2026-03-06-brainstorming-session.md`

---

## Spec Functional Requirements (FR1–FR14)

### FR1. Pipe-first invocation ✅ IMPLEMENTED
**Spec:** System must accept piped stdin as a first-class source.  
**Code:** `internal/cli/flags.go:75` — `Source` field; `internal/cli/cli.go` — `handlePipelineMode()` reads stdin when no `--source` or `--scrape_url` is provided. `internal/pipeline/types.go` — `SourceModeStdin = "stdin"`.  
**Evidence:** Pipeline runner resolves stdin payload via `resolveStageInput()` in `runner.go` when source mode is stdin.

### FR2. URL-driven invocation ✅ IMPLEMENTED
**Spec:** System must accept URL input and route through Fabric's scrape flow.  
**Code:** `internal/cli/flags.go:29` — `ScrapeUrl` flag; `internal/pipeline/types.go` — `SourceModeScrapeURL = "scrape_url"`. CLI dispatches URL scraping before pipeline entry when `--scrape_url` is set.  
**Evidence:** `accepts:` field in YAML supports `scrape_url`.

### FR3. File and directory invocation ✅ IMPLEMENTED
**Spec:** System must accept direct file or directory paths.  
**Code:** `internal/cli/flags.go:75` — `Source string` flag; `internal/pipeline/types.go` — `SourceModeSource = "source"`.  
**Evidence:** All built-in pipelines declare `accepts: [stdin, source]` or include source.

### FR4. Stage-aware execution ✅ IMPLEMENTED
**Spec:** System must execute and report an explicit, linear stage model with explicit id, executor type, and exactly one final output stage.  
**Code:**  
- `internal/pipeline/types.go:45-74` — `Stage` struct with fields: `ID string`, `Executor ExecutorType`, `FinalOutput bool`
- `internal/pipeline/validate.go` — enforces exactly one `FinalOutput: true` stage
- `internal/pipeline/runner.go` — linear sequential loop over `selectedStageIndices`
- Stage IDs validated as unique in `validate.go`

### FR5. Stage UI visibility ✅ IMPLEMENTED
**Spec:** Terminal UI must show current stage, stage status, stream output, files written, final PASS/FAIL.  
**Code:** `internal/pipeline/runner.go` — `renderStageStart()`, `renderStageResult()`, `renderRunSummary()` functions emit stage progress markers to stderr. Format: `[N/M] stage-id ... PASS/FAIL`.

### FR6. Multi-mode execution ✅ IMPLEMENTED
**Spec:** Support quick `--pattern` and full `--pipeline` execution.  
**Code:** `internal/cli/cli.go` — `handlePipelineMode()` is called when `Pipeline != ""`, otherwise falls through to normal pattern execution via `handlePatternMode()`.

### FR7. External pipeline compatibility ✅ IMPLEMENTED
**Spec:** Support using existing external pipelines through stage adapters.  
**Code:** `internal/pipeline/executor.go` — `executeCommandStage()` runs arbitrary executables with `exec.CommandContext()`. Supports `program`, `args`, `cwd`, `env`, `timeout`.  
**Evidence:** `zoom-tech-note.yaml` wraps Python scripts via command executor.

### FR8. Artifact preservation ✅ IMPLEMENTED
**Spec:** Full pipeline runs must write artifacts under `.pipeline/<run-id>/`.  
**Code:**  
- `internal/pipeline/cleanup.go:17` — `PipelineDir = ".pipeline"`
- `internal/pipeline/cleanup.go` — `CreateRunDir()` creates `.pipeline/<run-id>/`
- `internal/pipeline/runner.go` — writes `run_manifest.json`, `source_manifest.json`, `run.json`
- Declared named artifacts tracked in `stageArtifacts` map

### FR9. Profile support ✅ IMPLEMENTED
**Spec:** Must support at minimum technical-study-guide and nontechnical-study-guide.  
**Code:** `data/pipelines/technical-study-guide.yaml` and `data/pipelines/nontechnical-study-guide.yaml` exist plus 5 more profiles (passthrough, zoom-tech-note, zoom-tech-note-deep-pass, note-enhancement, therapy-conversation-notes).

### FR10. Output control ✅ IMPLEMENTED
**Spec:** Operator must be able to choose stdout and -o/--output.  
**Code:** `internal/cli/cli.go` — `handlePipelineMode()` calls `writePipelineOutput()` which writes to file via `-o` AND emits to stdout. Runner's stdout is `os.Stdout` for final payload.  
**Evidence:** `-o` never suppresses stdout, per brainstorming clarification #4.

### FR11. Custom pipeline support ✅ IMPLEMENTED
**Spec:** User-defined pipelines in `~/.config/fabric/pipelines/`, loadable without recompiling, override built-ins, discoverable via `--listpipelines`, validatable.  
**Code:**  
- `internal/pipeline/loader.go:26-27` — `builtinPipelinesDir = "data/pipelines"`, `userPipelinesDir = "pipelines"` (under config home)
- `loader.go:LoadAll()` — loads from both dirs, user overrides built-in by name
- `loader.go:LoadAll()` emits `fmt.Fprintf(os.Stderr, "info: using user-defined pipeline '%s'...")` on override
- `internal/cli/cli.go` — handles `--listpipelines`, `--validate-pipeline`, `--validate-only`

### FR12. Polyglot command execution ✅ IMPLEMENTED
**Spec:** Command stages must run executables in any language (Python, Bash, Java, Node, etc.).  
**Code:** `internal/pipeline/executor.go` — `executeCommandStage()` uses `exec.CommandContext(ctx, program, args...)`. Supports:
- `Command.Program` (string) — executable path
- `Command.Args` ([]string) — argument list
- `Command.Cwd` (string) — optional working directory
- `Command.Env` (map[string]string) — stage-level environment
- `Command.Timeout` (int) — per-stage timeout in seconds
- Stdout and stderr captured separately
- Exit code checked for failure

### FR13. Schema versioning ✅ IMPLEMENTED
**Spec:** Pipeline definitions must declare a schema version.  
**Code:** `internal/pipeline/types.go:22` — `Version int` field; `internal/pipeline/validate.go` — checks `p.Version >= 1`.

### FR14. Pipeline definition language ✅ IMPLEMENTED
**Spec:** YAML, `.yaml` extension, mandatory name matching filename stem, validated against versioned schema + semantic preflight.  
**Code:**  
- `internal/pipeline/loader.go` — uses `yaml.Unmarshal` to parse, only loads `.yaml` files (line 57: `filepath.Ext(entry.Name()) == ".yaml"`)
- `internal/pipeline/validate.go` — checks `p.Name == p.FileStem` (name must match filename stem)
- `internal/pipeline/preflight.go` — runs `Validate()` then semantic checks

---

## Spec Non-Functional Requirements (NFR1–NFR11)

| NFR | Requirement | Status | Evidence |
|-----|------------|--------|----------|
| NFR1 | Fabric-first architecture | ✅ | Fabric remains the only binary; pipeline runner lives inside Fabric |
| NFR2 | Minimal invasive change | ✅ | Pipeline code in `internal/pipeline/` package, CLI integration minimal |
| NFR3 | Upgrade safety | ✅ | User pipelines in `~/.config/fabric/pipelines/`, separate from built-ins |
| NFR4 | Observability | ✅ | Stage progress on stderr, JSON events via `--pipeline-events-json`, manifests |
| NFR5 | Reproducibility | ✅ | Deterministic stages produce deterministic artifacts |
| NFR6 | Privacy | ✅ | All execution local by default |
| NFR7 | Extensibility | ✅ | New pipelines addable as YAML, new executors via registry |
| NFR8 | Low operator overhead | ✅ | Simple `fabric --pipeline <name>` invocation |
| NFR9 | Explicit failure semantics | ✅ | Stage-specific errors with stage ID, executor type, exit code |
| NFR10 | Scalability | ✅ | New definitions/profiles/executors without core changes |
| NFR11 | Upgrade-safe customization | ✅ | User pipelines never overwritten by Fabric updates |

---

## 44 Settled Design Clarifications Verification

### Clarification 1: Input Source Policy ✅
**Spec:** `--pipeline` must require exactly one input source (stdin, --source, --scrape_url).  
**Code:** `internal/cli/cli.go` — `validatePipelineSources()` enforces exactly one source; rejects multiple simultaneous sources.

### Clarification 2: Chaining Through Pipes ✅
**Spec:** stdout contains only final payload; stderr contains stage UI, progress, warnings.  
**Code:** `internal/pipeline/runner.go` — stdout written only via `emitFinalOutput()` for the final_output stage. All progress via `renderStageStart()`/`renderStageResult()`/`renderRunSummary()` go to stderr.

### Clarification 3: Artifact Location & Cleanup ✅
**Spec:** `.pipeline/<run-id>/` in CWD with 5-second hybrid cleanup.  
**Code:**  
- `cleanup.go:17` — `PipelineDir = ".pipeline"`
- `cleanup.go:18` — `cleanupDelay = 5 * time.Second`
- `cleanup.go` — `CreateRunDir()`, `scheduleCleanup()` (delayed), `CleanupStaleRuns()` (janitor)
- `cleanup.go` — janitor checks `run.json` for `expires_at` and deletes expired dirs
- `cleanup.go` — removes `.pipeline/` itself only if empty after per-run cleanup

### Clarification 4: `-o` Meaning ✅
**Spec:** `-o` writes final output to file AND still emits to stdout.  
**Code:** `internal/cli/cli.go` — `writePipelineOutput()` writes to file, then `emitFinalOutput()` also writes to stdout. Never suppresses chaining.

### Clarification 5: `-o` Must Not Control Artifact Rooting ✅
**Spec:** `-o` controls only final output file, not `.pipeline/` location.  
**Code:** `.pipeline/` always created in CWD regardless of `-o` path. No code connects `-o` to artifact root.

### Clarification 6: Exactly One Final Output Stage ✅
**Spec:** Each pipeline must declare exactly one `final_output: true` stage.  
**Code:** `internal/pipeline/validate.go` — `finalOutputCount` variable; if count != 1, returns error `"exactly one stage must have final_output: true"`.

### Clarification 7: Validation Must Gate Final Stdout ✅
**Spec:** If a validate stage exists, validation must pass before final stdout emission.  
**Code:** `internal/pipeline/runner.go` — After the final_output stage completes, the runner continues executing validate/publish stages. The `emitFinalOutput()` call is gated by `validationSatisfied` flag. If validate stage fails, final output is NOT emitted to stdout.

### Clarification 8: Pipelines Without Validate Stage ✅
**Spec:** Pipeline may omit validate; Fabric emits warning on stderr before releasing payload.  
**Code:** `internal/pipeline/runner.go` — checks if any stage has `Role == StageRoleValidate`. If not, emits `fmt.Fprintf(r.Stderr, "warning: pipeline %s has no validate stage\n", ...)` and sets `validationSatisfied = true`.

### Clarification 9: Validation-Absence Warning Format ✅
**Spec:** Warning must be plain informational stderr line, not a fake stage.  
**Code:** Warning is a simple `fmt.Fprintf(r.Stderr, ...)` call, not modeled as a stage event.

### Clarification 10: Publish Failure After Validated Output ✅
**Spec:** If validate passes but publish fails, stdout may still emit validated payload; exit non-zero.  
**Code:** `internal/pipeline/runner.go` — publish stages execute after validate. If publish fails, `failRun()` is called but `finalOutput` was already emitted to stdout after validation passed. Non-zero exit code propagated.

### Clarification 11: Stage Names Are Conventions ✅
**Spec:** Names like `intake`, `normalize` are not reserved; behavior from metadata, not names.  
**Code:** `internal/pipeline/types.go` — no name-based behavior. Role semantics come from `Stage.Role` field, not `Stage.ID`.

### Clarification 12: Publish Is Optional ✅
**Code:** No validation requires a publish stage. Built-in `passthrough.yaml` has zero publish stages.

### Clarification 13: Pipelines May Be Entirely Command-Driven ✅
**Spec:** Zero `fabric_pattern` stages is valid.  
**Code:** No validation requires at least one `fabric_pattern` stage. A pipeline with all `command` executors would pass preflight.

### Clarification 14: V1 Pipelines Strictly Linear ✅
**Code:** `runner.go` — single `for` loop over stages in order. No branching, fan-out, or parallel execution.

### Clarification 15: Command Stages Fully Trusted ✅
**Spec:** May write/delete outside `.pipeline/<run-id>/`.  
**Code:** `executor.go` — `executeCommandStage()` runs programs with full host permissions via `exec.CommandContext`. No sandboxing.

### Clarification 16: Hybrid Handoff Contract ✅
**Spec:** Each stage produces primary payload + optional artifacts.  
**Code:** `runner.go` — maintains `stagePayloads map[string]string` for primary outputs and `stageArtifacts map[string]map[string]string` for artifacts. Both tracked per stage ID.

### Clarification 17: Primary Output Source Declared ✅
**Spec:** When a stage can produce stdout and artifact files, must explicitly declare which is primary.  
**Code:** `types.go` — `PrimaryOutput` struct with `From PrimaryOutputFrom` field (stdout or artifact) and `Artifact string`.

### Clarification 18: Stage Input Defaults ✅
**Spec:** Default is previous stage's primary output; may read earlier named artifacts.  
**Code:** `runner.go` — `resolveStageInput()` defaults to previous stage payload. If `stage.Input.From == StageInputArtifact`, resolves from named artifact of specified earlier stage.

### Clarification 19: Same Schema for Built-in and User ✅
**Code:** Same `Pipeline` struct, same `Validate()`, same `Preflight()` for both.

### Clarification 20: Override Visibility ✅
**Spec:** User overrides built-in by name with informational stderr.  
**Code:** `loader.go:LoadAll()` — `fmt.Fprintf(os.Stderr, "info: using user-defined pipeline '%s' instead of built-in definition\n", name)`.

### Clarification 21: Env Vars From Process Environment ✅
**Code:** `executor.go` — command stages inherit `os.Environ()` by default, then overlay stage-level `env` map. `preflight.go` expands env vars via `os.ExpandEnv()`.

### Clarification 22: Mandatory Preflight Validation ✅
**Code:** `preflight.go:Preflight()` called before every pipeline run. Also exposed as `--validate-pipeline` and `--validate-only`.

### Clarification 23: Preflight Side-Effect Free ✅
**Spec:** No AI calls, no script execution.  
**Code:** `preflight.go` — only does: validate schema, check file existence (patterns, executables), expand env vars, check stat() on paths. No network calls, no process execution.

### Clarification 24: YAML Pipeline Definitions ✅
**Code:** `loader.go` — `yaml.Unmarshal`. All 7 built-in definitions are `.yaml` files.

### Clarification 25: `--listpipelines` Dedicated Flag ✅
**Code:** `flags.go:51` — `ListPipelines bool`. Follows Fabric convention alongside `--listpatterns`, `--listmodels`, etc.

### Clarification 26: User Pipelines in `~/.config/fabric/pipelines/` ✅
**Code:** `loader.go:27` — `userPipelinesDir = "pipelines"` resolved under `configHome` (defaults to `~/.config/fabric/`).

### Clarification 27: `.yaml` Extension Only ✅
**Code:** `loader.go:57` — `filepath.Ext(entry.Name()) == ".yaml"` — only `.yaml` files loaded.

### Clarification 28: Name Must Match Filename Stem ✅
**Code:** `validate.go` — `if p.Name != p.FileStem` returns error.

### Clarification 29: Every Stage Must Declare Explicit ID ✅
**Code:** `validate.go` — `if s.ID == ""` returns error. Uniqueness enforced via `seenIDs` map.

### Clarification 30: Explicit Executor Field ✅
**Code:** `validate.go` — validates `s.Executor` against allowed types; rejects unknown values.

### Clarification 31: Structured `program` + `args` ✅
**Code:** `types.go` — `CommandConfig` struct with `Program string` and `Args []string`. Not a raw shell string. `executor.go` — `exec.CommandContext(ctx, cfg.Program, cfg.Args...)`.

### Clarification 32: Optional `cwd` ✅
**Code:** `types.go` — `CommandConfig.Cwd string`. `executor.go` — `cmd.Dir = cfg.Cwd` when non-empty; defaults to current directory.

### Clarification 33: Stage-Level `env` Map ✅
**Code:** `types.go` — `CommandConfig.Env map[string]string`. `executor.go` — inherited process env + stage overlay.

### Clarification 34: Optional Per-Stage `timeout` ✅
**Code:** `types.go` — `CommandConfig.Timeout int`. `executor.go` — creates `context.WithTimeout()` with the declared seconds. `validate.go` — `Timeout >= 0`.

### Clarification 35: Top-Level Schema ✅
**Code:** `types.go` — `Pipeline` struct: `Version int` (required), `Name string` (required), `Stages []Stage` (required), `Description string` (optional), `Accepts []SourceMode` (optional).

### Clarification 36: Stage Input Object ✅
**Code:** `types.go` — `StageInput` struct: `From StageInputFrom`, `Stage string`, `Artifact string`.

### Clarification 37: Named Artifacts ✅
**Code:** `types.go` — `ArtifactDecl` struct: `Name string`, `Path string`, `Required *bool`. Path relative to `.pipeline/<run-id>/`.

### Clarification 38: Primary Output ✅
**Code:** `types.go` — `PrimaryOutput` struct: `From PrimaryOutputFrom`, `Artifact string`.

### Clarification 39: Fabric-Pattern Stage Schema ✅
**Code:** `types.go` — `Stage` has: `Pattern string`, `Context string`, `Strategy string`, `Variables map[string]string`, `Stream bool`.

### Clarification 40: Builtin Stages ✅
**Code:** `types.go` — `BuiltinConfig` struct: `Name string`, `Config map[string]interface{}`. `builtins.go` — registry with implementations: `passthrough`, `source_capture`, `validate_declared_outputs`, `write_publish_manifest`.

### Clarification 41: Command Stdout Captured ✅
**Code:** `executor.go` — `cmd.Stdout = &stdoutBuf` captures command stdout. Only becomes primary payload when `PrimaryOutput.From == PrimaryOutputStdout`.

### Clarification 42: Validation Commands ✅
**Code:** `cli.go` — `--validate-pipeline` exits 0 on valid, non-zero on invalid. Human-readable result on stdout, errors on stderr.

### Clarification 43: Shell-Complete Integration ✅
**Code:** `cli.go` — `--listpipelines` combined with `--shell-complete-list` emits raw pipeline names only.

### Clarification 44: V1 Boundary ✅
All Phase 1/2/3 items are implemented.

---

## Built-in Pipeline Verification

| Pipeline | Stages | Final Output | Roles | Accepts | YAML Valid |
|----------|--------|-------------|-------|---------|------------|
| passthrough | 1 (builtin:passthrough) | passthrough | none | stdin, source, scrape_url | ✅ |
| zoom-tech-note | 11 (mixed command/fabric_pattern) | stage3_enhance_materialize | validate, publish | stdin, source | ✅ |
| zoom-tech-note-deep-pass | 12 (adds deep_pass) | stage3_enhance_materialize | validate, publish | stdin, source | ✅ |
| technical-study-guide | 6 (mixed command/fabric_pattern/builtin) | study_guide_generate | validate | stdin, source | ✅ |
| nontechnical-study-guide | 6 (mixed) | study_guide_generate | validate | stdin, source | ✅ |
| note-enhancement | 4 (mixed) | enhance_generate | validate | stdin, source | ✅ |
| therapy-conversation-notes | 5 (mixed) | therapy_generate | validate | stdin, source | ✅ |

---

## Test Coverage Summary

| Test File | What It Verifies |
|-----------|-----------------|
| `pipeline_test.go` | Loader, preflight, validation, runner lifecycle, cleanup |
| `zoom_tech_note_test.go` | Zoom parity: prepare, ingest, Stage 1/2/3 materialize, deep pass, validate, publish |
| `technical_study_guide_test.go` | Study guide pipeline definition, preflight, stage flow |
| `nontechnical_study_guide_test.go` | Non-tech variant definition and preflight |
| `note_enhancement_test.go` | Enhancement pipeline definition and preflight |
| `therapy_conversation_notes_test.go` | Therapy pipeline with optional context/PDF |
| `loader_helpers_test.go` | File loading, discovery, override logic |
| `preflight_helpers_test.go` | Preflight validation checks |
| `runtime_helpers_test.go` | Runtime context, artifact resolution |
| `validate_selection_test.go` | Stage slicing validation |
| `validation_helpers_test.go` | Validation gating, role ordering |

**All tests pass:** `go test ./...` — zero failures, zero skips.

---

## Verification Commands Executed

```bash
go test ./internal/pipeline/... -count=1         # PASS (1.641s)
go test ./... -count=1                            # ALL PASS (zero failures)
python3 -m py_compile scripts/pipelines/zoom-tech-note/*.py  # ALL COMPILE
fabric --validate-pipeline data/pipelines/*.yaml  # ALL 7 VALID
```

---

## Conclusion

**Every functional requirement (FR1–FR14), non-functional requirement (NFR1–NFR11), and all 44 settled design clarifications from the brainstorming session are verified as implemented in the current branch with code-level evidence.**

The branch `feat/fabric-executable-pipelines` is implementation-complete and test-verified.
