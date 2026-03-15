# Fabric Local Transcription Cache SPEC

Status: Draft for implementation  
Date: 2026-03-14  
Scope: Fabric-native local transcription cache, model lifecycle, import, and first-run download behavior

## 1. Intake Summary

Here is what this document takes as given from prior discussion and code review:

1. Fabric already ships a remote speech-to-text path built around `--transcribe-file` and `--transcribe-model`, and that path is currently OpenAI-backed.
2. A separate local-first transcription system already exists outside Fabric and stores local model assets in a repo-local `.cache/models` tree.
3. For Fabric shipping, model ownership must move into Fabric-controlled paths rather than depending on another repository's cache layout.
4. For local development on the current machine, Fabric must support one-time reuse of already downloaded models so bandwidth is not wasted.
5. For new users, Fabric must auto-download missing models on first use and then reuse local cache on subsequent runs.
6. Fabric configuration and secrets must remain separate from large downloaded assets.

Important boundary:
This SPEC covers the cache and model lifecycle subsystem required for Fabric-native local transcription. It does not attempt to fully specify the entire downstream transcript-to-notes pipeline in this document.

## 2. Problem Statement

Fabric currently supports speech-to-text transcription only through remote transcription models. The existing implementation does not own a local model cache, does not provide a Fabric-native import path for already downloaded local Whisper or pyannote assets, and does not define first-run model installation behavior for local transcription execution.

Without a formal cache contract, future local transcription support would be fragile in four ways:

1. Model assets could end up stored in ad hoc directories with no stable ownership boundary.
2. Large binary assets could be mixed with config and secrets under `~/.config/fabric`.
3. Users who already downloaded local models in another tool would be forced to redownload them.
4. Operators would have no deterministic way to understand what Fabric will download, where it will store it, and how it will recover from partial installs.

This SPEC defines a Fabric-owned, cross-platform cache contract and operator-facing lifecycle for local transcription model assets.

## 3. Goals and Non-Goals

### 3.1 Goals

1. Define a Fabric-owned cache root for local transcription assets.
2. Preserve backward compatibility for the existing remote OpenAI transcription flow.
3. Enable one-time import of compatible local model caches that were downloaded outside Fabric.
4. Enable first-run download of missing local model assets into Fabric's cache.
5. Keep large downloaded assets out of `~/.config/fabric`.
6. Provide deterministic CLI behavior for local transcription setup, model listing, import, download, and cache inspection.
7. Support Apple Silicon-first backend selection with `mlx-whisper` preferred on Apple Silicon and `faster-whisper` as fallback.
8. Support optional diarization asset lifecycle for `pyannote/speaker-diarization-community-1`.
9. Emit clear status and recovery guidance for import failures, partial downloads, invalid cache contents, and missing credentials.

### 3.2 Non-Goals

1. Replacing the existing remote OpenAI transcription path in the first increment.
2. Defining the full diarization runtime algorithm in this document beyond asset lifecycle and execution prerequisites.
3. Defining the entire human-readable cleanup pass in this document.
4. Defining transcript bundle formatting beyond what local transcription setup needs to hand work off to later pipeline stages.
5. Supporting arbitrary third-party model stores in the first increment.

## 4. System Overview

The subsystem introduced by this SPEC adds a local transcription layer alongside the current remote transcription path.

### 4.1 Components

1. `CLI transcription surface`
   Resolves user intent, chosen transcription engine, optional local backend, model name, import path, and setup mode.

2. `Transcription config resolver`
   Loads defaults from `~/.config/fabric/config.yaml`, environment variables, and CLI flags.

3. `Cache path resolver`
   Computes Fabric-owned cache directories using the host operating system's cache directory conventions.

4. `Local model catalog`
   Maps logical Fabric transcription model names to backend-specific assets and install state.

5. `Model installer`
   Downloads missing local model assets into Fabric cache.

6. `External cache importer`
   Validates an external cache path, copies compatible assets into Fabric cache, and records import metadata.

7. `Backend selector`
   Chooses `mlx-whisper` or `faster-whisper` for transcription execution.

8. `Prepared audio manager`
   Owns temporary or reusable prepared media assets used during local transcription.

9. `Downstream transcript handoff`
   Returns transcript text to the existing Fabric CLI flow and later pipeline stages.

### 4.2 High-Level Flow

1. User invokes a transcription-related command.
2. Fabric resolves whether the request uses the existing remote path or the new local path.
3. If local transcription is requested, Fabric resolves cache roots and model metadata.
4. Fabric checks whether required assets exist in Fabric cache.
5. If missing, Fabric either:
   - imports assets from an explicitly provided external cache path, or
   - downloads them into Fabric cache.
6. Fabric runs local transcription using the selected backend.
7. Fabric writes prepared media artifacts under Fabric cache and cleans them according to policy.
8. Fabric returns transcript text to the caller or downstream processing flow.

## 5. Core Domain Model

### 5.1 `CacheRoots`

| Field | Type | Required | Default | Validation |
|---|---|---:|---|---|
| `config_dir` | string | yes | `~/.config/fabric` | Must be an absolute path after expansion |
| `cache_root` | string | yes | `<os.UserCacheDir()>/fabric` | Must be an absolute path after expansion |
| `model_cache_dir` | string | yes | `<cache_root>/models` | Must be a descendant of `cache_root` |
| `prepared_audio_dir` | string | yes | `<cache_root>/transcription/prepared` | Must be a descendant of `cache_root` |
| `metadata_dir` | string | yes | `<cache_root>/transcription/metadata` | Must be a descendant of `cache_root` |

Important nuance:
`config_dir` and `cache_root` are distinct ownership zones. Config, defaults, and secrets belong under `config_dir`. Downloaded models and prepared media belong under `cache_root`.

### 5.2 `LocalModelSpec`

| Field | Type | Required | Default | Validation |
|---|---|---:|---|---|
| `logical_name` | string | yes | none | Must match `^[a-z0-9._-]+$` |
| `backend` | enum | yes | none | One of `mlx-whisper`, `faster-whisper`, `pyannote` |
| `remote_identifier` | string | yes | none | Must be non-empty |
| `relative_cache_path` | string | yes | none | Must be relative, never absolute |
| `required_for_default_flow` | boolean | yes | `false` | No extra validation |
| `family` | enum | yes | none | One of `transcription`, `diarization` |
| `install_method` | enum | yes | none | One of `lazy-download`, `import-only`, `hf-download` |

### 5.3 `LocalModelInstallState`

| Field | Type | Required | Default | Validation |
|---|---|---:|---|---|
| `logical_name` | string | yes | none | Must correspond to a known `LocalModelSpec` |
| `status` | enum | yes | `missing` | One of `missing`, `imported`, `downloaded`, `corrupt`, `partial` |
| `resolved_path` | string | no | none | Must be absolute when present |
| `source_kind` | enum | no | none | One of `fabric-cache`, `external-import`, `download` |
| `source_path` | string | no | none | Absolute path when present |
| `installed_at` | RFC3339 string | no | none | Must parse as RFC3339 when present |
| `manifest_version` | integer | yes | `1` | Must equal `1` in V1 |

### 5.4 `ImportRequest`

| Field | Type | Required | Default | Validation |
|---|---|---:|---|---|
| `source_root` | string | yes | none | Must exist and be a directory |
| `copy_mode` | enum | yes | `copy` | Only `copy` is supported in V1 |
| `families` | array of enum | yes | `["transcription"]` | Items from `transcription`, `diarization` |
| `overwrite_existing` | boolean | yes | `false` | No extra validation |

Important boundary:
V1 does not support symlink-based import. Import means copying compatible cache contents into Fabric-owned cache.

### 5.5 `PreparedAudioArtifact`

| Field | Type | Required | Default | Validation |
|---|---|---:|---|---|
| `path` | string | yes | none | Must be absolute |
| `created_at` | RFC3339 string | yes | none | Must parse as RFC3339 |
| `cleanup_policy` | enum | yes | `always-delete` | One of `always-delete`, `always-keep`, `report-only` |
| `owner_run_id` | string | yes | none | Must be non-empty |

## 6. Local Transcription Contract

### 6.1 Cache Directory Contract

Fabric MUST compute its cache root using `os.UserCacheDir()` and append `fabric`.

Examples:

1. macOS:
   `~/Library/Caches/fabric`
2. Linux:
   `~/.cache/fabric`
3. Windows:
   `%LocalAppData%\\fabric`

Fabric MUST create these directories lazily when first needed:

1. `<cache_root>/models`
2. `<cache_root>/transcription/prepared`
3. `<cache_root>/transcription/metadata`

Fabric MUST NOT store downloaded model binaries under:

1. `~/.config/fabric`
2. the current working directory by default
3. a temporary directory

### 6.2 Model Families

V1 MUST support the following logical model families:

#### 6.2.1 Transcription

1. `large-v3` mapped to:
   - MLX backend asset: `mlx-community/whisper-large-v3-mlx`
   - Faster-Whisper backend asset: `Systran/faster-whisper-large-v3`

#### 6.2.2 Diarization

1. `speaker-diarization-community-1` mapped to:
   - `pyannote/speaker-diarization-community-1`

Important nuance:
The Fabric logical model name is backend-neutral. Backend-specific remote identifiers remain internal catalog data.

### 6.3 Install Ownership

1. If a required asset is already present and valid in Fabric cache, Fabric MUST reuse it.
2. If a required asset is not present in Fabric cache and the user provides an import source, Fabric MUST attempt import before download.
3. If a required asset is not present in Fabric cache and no import source is provided, Fabric MUST download the asset if auto-download is enabled.
4. If auto-download is disabled and the model is missing, Fabric MUST fail with an actionable setup error.

### 6.4 Import Contract

1. Import source paths are explicit user input in V1.
2. Fabric MUST validate that the source contains recognizable model directories before copying.
3. Fabric MUST copy into Fabric cache rather than execute from the external cache path.
4. Fabric MUST record import metadata in `<cache_root>/transcription/metadata/import-manifest.json`.
5. Fabric MUST NOT delete or mutate the external cache source.

### 6.5 Download Contract

1. Download target is always Fabric cache.
2. Downloads MUST be staged into a temporary sibling directory and atomically promoted into the final cache path after validation.
3. Partial downloads MUST be marked `partial` and cleaned up on the next attempt unless the operator asks to inspect them.
4. Failed downloads MUST never be treated as installed assets.

### 6.6 Prepared Audio Contract

1. Prepared media artifacts MUST live under `<cache_root>/transcription/prepared`.
2. V1 default cleanup policy is `always-delete`.
3. Prepared artifacts MUST never be stored inside model cache directories.
4. If a run fails after prepared audio creation, cleanup MUST still execute unless policy is `always-keep` or `report-only`.

## 7. Configuration Specification

### 7.1 Resolution Order

Configuration MUST resolve in this order, highest precedence first:

1. CLI flags
2. environment variables
3. `~/.config/fabric/config.yaml`
4. hard-coded defaults

Secrets MUST NOT be persisted automatically into `config.yaml`.

### 7.2 CLI Surface

V1 MUST preserve these existing flags:

1. `--transcribe-file`
2. `--transcribe-model`
3. `--list-transcription-models`
4. `--split-media-file`

V1 MUST add these new flags:

1. `--transcription-engine`
   Type: enum  
   Values: `openai`, `local`  
   Default: `openai`

2. `--transcription-backend`
   Type: enum  
   Values: `auto`, `mlx-whisper`, `faster-whisper`  
   Default: `auto`

3. `--transcription-cache-dir`
   Type: string path  
   Default: none  
   Meaning: override computed Fabric model cache root for the current command

4. `--transcription-import-cache-from`
   Type: string path  
   Default: none  
   Meaning: explicit external cache source to import from before download

5. `--setup-local-transcription`
   Type: boolean  
   Default: `false`  
   Meaning: perform local transcription setup, including cache creation, optional import, and missing-model installation

6. `--transcription-no-auto-download`
   Type: boolean  
   Default: `false`  
   Meaning: fail instead of downloading missing assets

7. `--transcription-prepared-audio-policy`
   Type: enum  
   Values: `always-delete`, `always-keep`, `report-only`  
   Default: `always-delete`

### 7.3 Config Keys

Fabric config YAML MUST support:

```yaml
transcription:
  engine: openai
  local:
    backend: auto
    default_model: large-v3
    cache_dir: ""
    prepared_audio_dir: ""
    auto_download_missing_models: true
    prepared_audio_policy: always-delete
```

### 7.4 Environment Variables

V1 MUST support these environment variables:

1. `FABRIC_TRANSCRIPTION_ENGINE`
2. `FABRIC_LOCAL_TRANSCRIPTION_BACKEND`
3. `FABRIC_LOCAL_TRANSCRIPTION_CACHE_DIR`
4. `FABRIC_LOCAL_TRANSCRIPTION_PREPARED_AUDIO_DIR`
5. `FABRIC_LOCAL_TRANSCRIPTION_AUTO_DOWNLOAD`
6. `HF_TOKEN`
7. `HUGGINGFACE_HUB_TOKEN`

Important boundary:
Hugging Face tokens are read from environment only in V1. Fabric MUST NOT write them into `.env` or `config.yaml` automatically.

### 7.5 Config Cheat Sheet

| Key | Type | Default |
|---|---|---|
| `transcription.engine` | enum | `openai` |
| `transcription.local.backend` | enum | `auto` |
| `transcription.local.default_model` | string | `large-v3` |
| `transcription.local.cache_dir` | string | empty, meaning computed from `os.UserCacheDir()` |
| `transcription.local.prepared_audio_dir` | string | empty, meaning computed from cache root |
| `transcription.local.auto_download_missing_models` | boolean | `true` |
| `transcription.local.prepared_audio_policy` | enum | `always-delete` |

## 8. State Machine and Lifecycle

### 8.1 `LocalModelInstallState.status`

1. `missing`
   Trigger: no valid model directory found
2. `partial`
   Trigger: temporary or incomplete download detected
3. `corrupt`
   Trigger: final directory exists but required validation files are missing
4. `imported`
   Trigger: explicit import completed and validation passed
5. `downloaded`
   Trigger: download completed and validation passed

### 8.2 Transitions

1. `missing -> imported`
   Trigger: successful import
2. `missing -> downloaded`
   Trigger: successful download
3. `missing -> partial`
   Trigger: interrupted or failed install created partial content
4. `partial -> downloaded`
   Trigger: successful retry with cleanup
5. `partial -> imported`
   Trigger: operator retries with import and validation succeeds
6. `downloaded -> corrupt`
   Trigger: later validation failure
7. `imported -> corrupt`
   Trigger: later validation failure
8. `corrupt -> downloaded`
   Trigger: delete invalid directory and redownload
9. `corrupt -> imported`
   Trigger: delete invalid directory and reimport

## 9. Core Algorithms

### 9.1 Cache Root Resolution

```text
function resolve_cache_roots(cli_flags, env, config):
    config_dir = "~/.config/fabric"
    cache_root = join(os_user_cache_dir(), "fabric")

    if config.transcription.local.cache_dir is non-empty:
        cache_root = config.transcription.local.cache_dir
    if env.FABRIC_LOCAL_TRANSCRIPTION_CACHE_DIR is non-empty:
        cache_root = env.FABRIC_LOCAL_TRANSCRIPTION_CACHE_DIR
    if cli_flags.transcription_cache_dir is non-empty:
        cache_root = cli_flags.transcription_cache_dir

    cache_root = expand_and_abs(cache_root)
    model_cache_dir = join(cache_root, "models")

    prepared_audio_dir = config.transcription.local.prepared_audio_dir
    if env override exists:
        prepared_audio_dir = env override
    if prepared_audio_dir is empty:
        prepared_audio_dir = join(cache_root, "transcription", "prepared")

    metadata_dir = join(cache_root, "transcription", "metadata")
    return CacheRoots(...)
```

### 9.2 Asset Resolution Before Local Run

```text
function ensure_local_assets(request):
    required_specs = catalog.resolve(request.model, request.backend, request.enable_diarization)

    for each spec in required_specs:
        state = inspect_install_state(spec)
        if state is downloaded or imported:
            continue

        if request.import_source is present:
            try import(spec, request.import_source)
            re-check state
            if installed:
                continue

        if request.auto_download is false:
            raise model_not_installed

        download(spec)
        re-check state
        if not installed:
            raise model_install_failed
```

### 9.3 Install Promotion

```text
function promote_staged_install(staging_dir, final_dir):
    validate(staging_dir)
    if final_dir exists:
        remove(final_dir)
    rename(staging_dir, final_dir)
    write_install_manifest(final_dir)
```

## 10. Integration Contracts

### 10.1 Current Fabric STT Integration

The existing remote transcription path in [transcribe.go](internal/cli/transcribe.go) and [openai_audio.go](internal/plugins/ai/openai/openai_audio.go) MUST remain functional and unchanged by default.

Backward-compatibility rule:

1. If `--transcription-engine` is omitted, Fabric behaves exactly as it does today.
2. Local transcription behavior is only activated when the resolved transcription engine is `local`.

### 10.2 External Cache Compatibility

V1 import MUST recognize cache layouts equivalent to:

1. Hugging Face hub-style directories for MLX and pyannote assets.
2. Faster-Whisper cache directories containing downloaded model assets.

The following local migration shape MUST be supported as an example compatibility target:

1. `.../huggingface/hub/models--mlx-community--whisper-large-v3-mlx`
2. `.../huggingface/hub/models--pyannote--speaker-diarization-community-1`
3. `.../models--Systran--faster-whisper-large-v3`

### 10.3 Backend Runtime Contracts

1. `mlx-whisper` is preferred on Apple Silicon when available.
2. `faster-whisper` is the fallback backend when:
   - host is not Apple Silicon, or
   - MLX runtime is unavailable, or
   - operator explicitly selects `faster-whisper`
3. `pyannote` requires a valid Hugging Face token when download is needed.

## 11. Subsystem Contracts

### 11.1 Cache Path Resolver

In scope:

1. resolve config and cache paths
2. expand `~`
3. return absolute paths
4. create directories lazily

Out of scope:

1. downloading models
2. validating model contents

### 11.2 Model Catalog

In scope:

1. define logical-to-physical model mapping
2. report install state
3. drive list commands

Out of scope:

1. backend execution

### 11.3 External Cache Importer

In scope:

1. validate source path
2. detect compatible model directories
3. copy into Fabric cache
4. record import metadata

Out of scope:

1. mutating source cache
2. symlink import in V1

### 11.4 Model Installer

In scope:

1. download missing assets
2. stage and promote installs
3. validate install completeness

Out of scope:

1. remote inference
2. transcript formatting

## 12. Logging, Status, and Observability

Fabric MUST emit operator-readable status for:

1. cache root resolution
2. model cache hit
3. explicit import start and completion
4. model download start and completion
5. prepared audio cleanup decisions
6. validation failure and recovery suggestion

At debug level 1 or higher, Fabric SHOULD print:

1. selected transcription engine
2. selected local backend
3. selected logical model
4. resolved final cache paths

At debug level 2 or higher, Fabric SHOULD print:

1. import source path
2. validation probe details
3. cleanup actions on partial installs

## 13. Failure Model and Recovery Strategy

| Error Category | Trigger | Recovery |
|---|---|---|
| `invalid_transcription_cache_dir` | cache override path is invalid or unwritable | fail fast with path-specific guidance |
| `external_cache_not_found` | import source does not exist | fail fast; user must provide a valid source |
| `external_cache_incompatible` | import source contains no recognizable model assets | fail fast; suggest known valid source shapes |
| `model_not_installed` | local model missing and auto-download disabled | instruct user to import or rerun without disable flag |
| `model_download_failed` | remote asset download fails | retry-safe; preserve source state, clean partial staging |
| `model_validation_failed` | installed files are incomplete or invalid | mark `corrupt`; advise reimport or redownload |
| `prepared_audio_cleanup_failed` | deletion of prepared media fails | warn and continue; do not fail successful transcription result |
| `hf_token_missing` | pyannote download requested without token | fail with explicit token guidance |

Important nuance:
Recovery must prefer deterministic operator action over magical silent fallback. V1 should be predictable before it is clever.

## 14. Security and Operational Safety

1. Fabric MUST never write Hugging Face tokens into logs.
2. Fabric MUST never persist tokens automatically into `config.yaml` or `.env`.
3. Import paths MUST be normalized to absolute paths before use.
4. Import logic MUST reject source paths that are files rather than directories.
5. Fabric MUST copy only recognized cache subtrees, not arbitrary directory contents.
6. Fabric MUST not remove external source caches.
7. Fabric MUST stage downloads before promotion to avoid half-installed final directories.

## 15. Reference Algorithms

### 15.1 Import Validation

```text
function validate_import_source(source_root, required_specs):
    found = []
    for each spec in required_specs:
        candidate = join(source_root, spec.relative_cache_path)
        if exists(candidate):
            if validate(candidate):
                found.append(spec.logical_name)

    if found is empty:
        raise external_cache_incompatible
    return found
```

### 15.2 Cleanup Partial Installs

```text
function cleanup_partial_install(final_dir, staging_dir):
    if staging_dir exists:
        remove_all(staging_dir)
    if final_dir is marked partial:
        remove_all(final_dir)
```

## 16. Test and Validation Matrix

### 16.1 Core Conformance

1. cache root resolves to OS cache directory by default
2. explicit CLI cache override wins over env and config
3. model cache never resolves under `~/.config/fabric` by default
4. explicit import copies compatible assets into Fabric cache
5. missing models trigger download when auto-download is enabled
6. missing models fail cleanly when auto-download is disabled
7. partial download is not treated as installed
8. corrupt install is detected and surfaced
9. prepared audio artifacts follow cleanup policy
10. remote OpenAI transcription path remains unchanged when local engine is not selected

### 16.2 Extension Conformance

1. pyannote asset install lifecycle works with valid token
2. Apple Silicon backend auto-selection prefers MLX when available
3. fallback to faster-whisper works when MLX is unavailable

### 16.3 Integration Profile

1. import existing external cache from standalone transcription repo
2. first-run download with no prior local assets
3. repeated run reuses already installed assets without download

## 17. Implementation Checklist

### 17.1 Required

1. Add cache root resolver based on `os.UserCacheDir()`
2. Add local transcription config schema and resolution
3. Add local model catalog for `large-v3`
4. Add optional pyannote catalog entry
5. Add explicit import command path
6. Add staged download and install validation
7. Add install metadata manifest
8. Add engine-aware transcription model listing
9. Add tests for cache resolution, import, download, validation, and backward compatibility
10. Update docs to explain config-vs-cache ownership clearly

### 17.2 Fast Follow

1. richer cache inspection command
2. optional cache prune command
3. broader model catalog beyond `large-v3`
4. richer local transcription bundle workflow

## Review Summary

- Sections: 17
- Spec focus: local transcription cache ownership, model lifecycle, import, and first-run download
- Main assumptions locked down:
  - Fabric owns the cache
  - config and cache remain separate
  - V1 import is copy-only
  - remote OpenAI STT remains the default path
- Remaining intentional follow-up areas:
  - full diarization runtime behavior
  - full transcript bundle contract
  - optional cache pruning UX
- Confidence: Ready for blueprint expansion and implementation planning
