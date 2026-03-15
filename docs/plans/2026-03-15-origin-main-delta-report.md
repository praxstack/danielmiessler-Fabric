# Delta Report: `origin/main` vs `feat/fabric-executable-pipelines`

**Date:** 2026-03-15  
**Branch under review:** `feat/fabric-executable-pipelines` (16 cherry-picked pipeline commits from `upstream/main`)  
**Compared against:** `origin/main` (your fork's main branch)

---

## Summary

There are **7 unique commits** on `origin/main` that are NOT in our `feat/fabric-executable-pipelines` branch. None are pipeline-related. Here is the full analysis.

---

## Commit 1: `0b796851` — fix(chat): unify strategy handling across server and cli

| Field | Value |
|-------|-------|
| **Author** | Prax Lannister |
| **Date** | 2026-03-14 |
| **PR** | #2061 (created during this session) |
| **Pipeline-related?** | Indirectly — fixes how `fabric_pattern` stages receive strategy context |
| **Files changed** | 4 files, +226 / -34 lines |

### Files Changed

| File | Change |
|------|--------|
| `internal/core/chatter.go` | +32 lines |
| `internal/core/chatter_test.go` | +130 lines |
| `internal/server/chat.go` | +53/-34 lines (net -19) |
| `internal/server/chat_test.go` | +45 lines (NEW) |

### Code Logic Introduced

1. **`recordFirstStreamError(errChan, err)`** — New helper in `chatter.go` that uses a non-blocking `select`/`default` to safely send only the first error to a buffered(1) channel. Prevents a **goroutine deadlock** when both the `SendStream` goroutine and the stream-update loop try to write errors simultaneously.

2. **`joinPromptSections(parts ...string)`** — New helper that trims whitespace from each prompt section (strategy, context, pattern), skips empty ones, and joins with `\n`. Replaces raw `strings.TrimSpace()` concatenation that could produce double-newlines or missing separators.

3. **`buildPromptChatRequest(p PromptRequest, language string)`** — Extracted from inline code in `HandleChat`. Now passes `StrategyName` through to `ChatRequest` so the core `Chatter.BuildSession()` handles strategy loading uniformly instead of the server doing it inline with `os.ReadFile`.

4. **Removed inline strategy loading** from `chat.go` — Previously the REST server was reading strategy JSON files directly and prepending them to `UserInput`. Now delegates to the core layer.

### Bug Fixed

**Streaming Deadlock:** When a vendor stream emits a `StreamTypeError` update AND `SendStream` returns an error, both try to write to `errChan` (buffer 1). The second write blocks forever → goroutine leak → `Chatter.Send` never returns → user sees a permanent hang.

### Tests Added

- `TestChatter_BuildSession_SeparatesSystemSections` — Verifies strategy+context+pattern joined with `\n` in correct order
- `TestChatter_Send_StreamingErrorUpdateAndReturnDoesNotDeadlock` — 2-second timeout regression test for the deadlock
- `TestBuildPromptChatRequest_PreservesStrategyAndUserInput` — Verifies extracted helper preserves all fields

---

## Commit 2: `3067af75` — feat(bedrock): dynamic region fetching and AWS_PROFILE fix

| Field | Value |
|-------|-------|
| **Author** | Prax Lannister |
| **Date** | 2026-03-07 |
| **PR** | #2052 (follow-up to #2044) |
| **Pipeline-related?** | No — Bedrock provider only |
| **Files changed** | 2 files, +87 / -8 lines |

### Files Changed

| File | Change |
|------|--------|
| `internal/plugins/ai/bedrock/bedrock.go` | +87/-4 lines |
| `internal/plugins/ai/bedrock/bedrock_test.go` | +2/-2 lines |

### Code Logic Introduced

1. **`fetchBedrockRegions()`** — New function that dynamically fetches AWS regions supporting Bedrock from botocore's public `endpoints.json` (no auth required). Parses the JSON to extract regions from the `bedrock` service entry, filters out FIPS/special endpoints, sorts alphabetically. Falls back to static `fallbackRegions` (6 regions) on any error.

2. **AWS_PROFILE conflict fix** — When using explicit credentials (bearer token or static keys), temporarily clears `AWS_PROFILE` env var before AWS SDK initialization and restores it via `defer`. This prevents "failed to get shared config profile" errors for users who have `AWS_PROFILE` set for other tools (terraform, aws-cli).

3. **Empty auth choice handling** — Returns `nil` instead of error when user presses Enter without typing at the auth selection prompt.

4. **Renamed** `awsRegions` → `fallbackRegions` to clarify intent.

---

## Commit 3: `8e7e3a0e` — fix(ollama): map thinking levels and convert single system-role messages

| Field | Value |
|-------|-------|
| **Author** | pretyflaco (upstream contributor) |
| **Date** | 2026-03-07 |
| **PR** | #2054 |
| **Pipeline-related?** | Indirectly — Ollama can be used as a vendor in pipeline `fabric_pattern` stages |
| **Files changed** | 1 file, +17 lines |

### Files Changed

| File | Change |
|------|--------|
| `internal/plugins/ai/ollama/ollama.go` | +17 lines |

### Code Logic Introduced

1. **Single system-role message conversion** — In `createChatRequest()`, if there's exactly 1 message with `role=system`, it's converted to `role=user`. Some models (qwen3-coder, deepseek) return empty responses when the only message is system-role.

2. **Thinking level mapping** — Maps Fabric's `ThinkingLevel` enum to Ollama's `Think` field:
   - `ThinkingOff` → `Think: false`
   - `ThinkingLow/Medium/High` → `Think: true`
   
   Previously Fabric's thinking levels were ignored by the Ollama provider.

---

## Commit 4: `59a17ce6` — fix: Manual edit of changelog.db and fixes for ChangeLog

| Field | Value |
|-------|-------|
| **Author** | Kayvan Sylvan (upstream maintainer) |
| **Date** | 2026-03-07 |
| **Pipeline-related?** | No — changelog maintenance |
| **Files changed** | 2 files, +10/-4 lines |

### Files Changed

| File | Change |
|------|--------|
| `CHANGELOG.md` | Formatting fixes (added blank lines between MAESTRO i18n entries, fixed indentation of list items) |
| `cmd/generate_changelog/changelog.db` | Binary update |

### Code Logic Introduced

None — purely formatting corrections to CHANGELOG.md:
- Added blank lines between MAESTRO i18n extraction entries for readability
- Fixed indentation of `extract_bd_ideas`, `suggest_gt_command`, `create_bd_issue` list items (were sub-indented, now top-level)
- Fixed broken `[dependabot]]` link (extra bracket)

---

## Commit 5: `345cd1c2` — chore: incoming 2054 changelog entry

| Field | Value |
|-------|-------|
| **Author** | Kayvan Sylvan |
| **Date** | 2026-03-07 |
| **Pipeline-related?** | No — changelog |
| **Files changed** | 1 file, +3 lines |

### Files Changed

| File | Change |
|------|--------|
| `cmd/generate_changelog/incoming/2054.txt` | NEW — 3-line changelog entry for PR #2054 (Ollama thinking levels fix) |

### Code Logic Introduced

None — staging file for automated changelog generation.

---

## Commit 6: `cfadecfb` — chore(release): Update version to v1.4.433

| Field | Value |
|-------|-------|
| **Author** | github-actions[bot] |
| **Date** | 2026-03-07 |
| **Pipeline-related?** | No — automated release |
| **Files changed** | 5 files, +12/-5 lines |

### Files Changed

| File | Change |
|------|--------|
| `CHANGELOG.md` | Added v1.4.433 section (Ollama PR #2054 + changelog fixes) |
| `cmd/fabric/version.go` | `v1.4.432` → `v1.4.433` |
| `cmd/generate_changelog/changelog.db` | Binary update |
| `cmd/generate_changelog/incoming/2054.txt` | DELETED (consumed by release) |
| `nix/pkgs/fabric/version.nix` | `1.4.432` → `1.4.433` |

### Code Logic Introduced

None — automated version bump by GitHub Actions release workflow.

---

## Commit 7: `a0cebce8` — chore(release): Update version to v1.4.434

| Field | Value |
|-------|-------|
| **Author** | github-actions[bot] |
| **Date** | 2026-03-09 |
| **Pipeline-related?** | No — automated release |
| **Files changed** | 5 files, +10/-7 lines |

### Files Changed

| File | Change |
|------|--------|
| `CHANGELOG.md` | Added v1.4.434 section (Bedrock PR #2052) |
| `cmd/fabric/version.go` | `v1.4.433` → `v1.4.434` |
| `cmd/generate_changelog/changelog.db` | Binary update |
| `cmd/generate_changelog/incoming/2052.txt` | DELETED (consumed by release) |
| `nix/pkgs/fabric/version.nix` | `1.4.433` → `1.4.434` |

### Code Logic Introduced

None — automated version bump by GitHub Actions release workflow.

---

## Recommendation Matrix

| Commit | Include in pipeline branch? | Rationale |
|--------|---------------------------|-----------|
| `0b796851` Strategy fix | ⚠️ Optional | Already in separate PR #2061. Including would add noise to the pipeline PR. |
| `3067af75` Bedrock regions | ❌ Skip | Bedrock-only, no pipeline impact |
| `8e7e3a0e` Ollama thinking | ⚠️ Optional | Useful for Ollama-backed pipeline stages, but upstream will merge this naturally |
| `59a17ce6` Changelog fixes | ❌ Skip | Formatting only |
| `345cd1c2` Changelog entry | ❌ Skip | Staging file |
| `cfadecfb` v1.4.433 | ❌ Skip | Automated release |
| `a0cebce8` v1.4.434 | ❌ Skip | Automated release |

**Bottom line:** No additional commits need to be cherry-picked into `feat/fabric-executable-pipelines`. The pipeline branch is complete and self-contained.
