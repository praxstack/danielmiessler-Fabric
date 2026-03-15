# Pipeline Rename and New Pipelines Plan

**Date:** 2026-03-15  
**Status:** Approved for implementation  
**Goal:** Generalize pipeline names and add 3 new flagship pipelines  
**Constraint:** Non-breaking — every rename is atomic (old name fully removed, new name fully consistent), tests pass at every step

---

## Part 1: Renames (4 pipelines)

Each rename is a self-contained atomic commit. The order does not matter.

### Rename 1: `therapy-conversation-notes` → `conversation-notes`

**Why:** Logic works for any conversation (therapy, coaching, interview, podcast). Drop domain bias.

**Files to change:**

| Category | Old | New |
|----------|-----|-----|
| YAML definition | `data/pipelines/therapy-conversation-notes.yaml` | `data/pipelines/conversation-notes.yaml` |
| YAML `name:` field | `name: therapy-conversation-notes` | `name: conversation-notes` |
| Scripts directory | `scripts/pipelines/therapy-conversation-notes/` | `scripts/pipelines/conversation-notes/` |
| Script docstrings | all `"""...therapy-conversation-notes..."""` | `"""...conversation-notes..."""` |
| Script error messages | `common.py` references | update to `conversation-notes` |
| Test file | `internal/pipeline/therapy_conversation_notes_test.go` | `internal/pipeline/conversation_notes_test.go` |
| Test references | `LoadNamed("therapy-conversation-notes")` | `LoadNamed("conversation-notes")` |
| Test paths | `scripts/pipelines/therapy-conversation-notes/` | `scripts/pipelines/conversation-notes/` |
| Smoke harness | `scripts/pipelines/live_smoke.py` line 80 | update pipeline name |
| YAML stage command paths | all `scripts/pipelines/therapy-conversation-notes/` refs in YAML | update to `conversation-notes` |

**Verification:** `go test ./internal/pipeline/... && fabric --validate-pipeline data/pipelines/conversation-notes.yaml`

---

### Rename 2: `note-enhancement` → `enhance-notes`

**Why:** Verb-first naming is more intuitive ("I want to enhance notes").

**Files to change:**

| Category | Old | New |
|----------|-----|-----|
| YAML definition | `data/pipelines/note-enhancement.yaml` | `data/pipelines/enhance-notes.yaml` |
| YAML `name:` field | `name: note-enhancement` | `name: enhance-notes` |
| Scripts directory | `scripts/pipelines/note-enhancement/` | `scripts/pipelines/enhance-notes/` |
| Script docstrings | all `"""...note-enhancement..."""` | `"""...enhance-notes..."""` |
| Test file | `internal/pipeline/note_enhancement_test.go` | `internal/pipeline/enhance_notes_test.go` |
| Test references | `LoadNamed("note-enhancement")` | `LoadNamed("enhance-notes")` |
| Test paths | `scripts/pipelines/note-enhancement/` | `scripts/pipelines/enhance-notes/` |
| Smoke harness | `scripts/pipelines/live_smoke.py` line 75 | update pipeline name |
| YAML stage command paths | all `scripts/pipelines/note-enhancement/` refs in YAML | update to `enhance-notes` |

**Verification:** `go test ./internal/pipeline/... && fabric --validate-pipeline data/pipelines/enhance-notes.yaml`

---

### Rename 3: `technical-study-guide` → `study-guide-technical`

**Why:** Groups study guides together alphabetically in `--listpipelines`.

**Files to change:**

| Category | Old | New |
|----------|-----|-----|
| YAML definition | `data/pipelines/technical-study-guide.yaml` | `data/pipelines/study-guide-technical.yaml` |
| YAML `name:` field | `name: technical-study-guide` | `name: study-guide-technical` |
| Scripts directory | `scripts/pipelines/technical-study-guide/` | `scripts/pipelines/study-guide-technical/` |
| Script docstrings/messages | any `technical-study-guide` references | update to `study-guide-technical` |
| Test file | `internal/pipeline/technical_study_guide_test.go` | `internal/pipeline/study_guide_technical_test.go` |
| Test references | `LoadNamed("technical-study-guide")` | `LoadNamed("study-guide-technical")` |
| Test paths | `scripts/pipelines/technical-study-guide/` | `scripts/pipelines/study-guide-technical/` |
| Smoke harness | `scripts/pipelines/live_smoke.py` line 65 | update pipeline name |
| YAML stage command paths | all `scripts/pipelines/technical-study-guide/` refs in YAML | update to `study-guide-technical` |

**Verification:** `go test ./internal/pipeline/... && fabric --validate-pipeline data/pipelines/study-guide-technical.yaml`

---

### Rename 4: `nontechnical-study-guide` → `study-guide-conceptual`

**Why:** "Conceptual" is clearer than "nontechnical". Groups with study-guide-technical.

**Files to change:**

| Category | Old | New |
|----------|-----|-----|
| YAML definition | `data/pipelines/nontechnical-study-guide.yaml` | `data/pipelines/study-guide-conceptual.yaml` |
| YAML `name:` field | `name: nontechnical-study-guide` | `name: study-guide-conceptual` |
| Scripts directory | `scripts/pipelines/nontechnical-study-guide/` | `scripts/pipelines/study-guide-conceptual/` |
| Script docstrings/messages | all `nontechnical-study-guide` references | update to `study-guide-conceptual` |
| Test file | `internal/pipeline/nontechnical_study_guide_test.go` | `internal/pipeline/study_guide_conceptual_test.go` |
| Test references | `LoadNamed("nontechnical-study-guide")` | `LoadNamed("study-guide-conceptual")` |
| Test paths | `scripts/pipelines/nontechnical-study-guide/` | `scripts/pipelines/study-guide-conceptual/` |
| Smoke harness | `scripts/pipelines/live_smoke.py` line 70 | update pipeline name |
| YAML stage command paths | all `scripts/pipelines/nontechnical-study-guide/` refs in YAML | update to `study-guide-conceptual` |

**Verification:** `go test ./internal/pipeline/... && fabric --validate-pipeline data/pipelines/study-guide-conceptual.yaml`

---

## Part 2: New General-Purpose Pipelines (3 pipelines)

Each new pipeline is a self-contained atomic commit.

### New Pipeline 1: `transcript-to-notes`

**Purpose:** THE flagship general-purpose pipeline. Any transcript (meeting, lecture, podcast, call) → structured notes.

**Design:**
```yaml
version: 1
name: transcript-to-notes
description: Convert any transcript into structured, readable notes.
accepts:
  - stdin
  - source
  - scrape_url
stages:
  - id: prepare_source
    executor: command
    command:
      program: python3
      args: ["scripts/pipelines/transcript-to-notes/prepare_source.py"]
    input:
      from: source
    primary_output:
      from: stdout
  - id: generate_notes
    executor: fabric_pattern
    pattern: transcript_to_notes
    stream: true
    final_output: true
    primary_output:
      from: stdout
  - id: validate_notes
    role: validate
    executor: builtin
    builtin:
      name: validate_declared_outputs
```

**New assets needed:**
- `data/pipelines/transcript-to-notes.yaml`
- `data/patterns/transcript_to_notes/system.md` — pattern prompt for general transcript→notes
- `scripts/pipelines/transcript-to-notes/prepare_source.py` — source preparation
- `internal/pipeline/transcript_to_notes_test.go` — definition + preflight test
- Update `scripts/pipelines/live_smoke.py` smoke entries

**Pattern prompt direction:** General-purpose, not tied to any domain. Should produce:
- Summary / Overview section
- Key Points with detail
- Action Items (if any)
- Notable Quotes / Highlights
- Participants (if identifiable)

---

### New Pipeline 2: `summarize`

**Purpose:** Universal summarization. Any text → structured summary.

**Design:**
```yaml
version: 1
name: summarize
description: Produce a structured summary from any input text.
accepts:
  - stdin
  - source
  - scrape_url
stages:
  - id: generate_summary
    executor: fabric_pattern
    pattern: pipeline_summarize
    stream: true
    final_output: true
    primary_output:
      from: stdout
```

**New assets needed:**
- `data/pipelines/summarize.yaml`
- `data/patterns/pipeline_summarize/system.md` — distinct from existing `summarize` pattern to avoid collision, or reuse if compatible
- `internal/pipeline/summarize_test.go` — definition + preflight test
- Update smoke harness

**Pattern prompt direction:** Structured output with:
- One-sentence TL;DR
- Executive summary (2-3 paragraphs)
- Key takeaways (bulleted)
- Details by section/topic

---

### New Pipeline 3: `extract-insights`

**Purpose:** Any text → themes, insights, and action items.

**Design:**
```yaml
version: 1
name: extract-insights
description: Extract themes, insights, and action items from any text.
accepts:
  - stdin
  - source
  - scrape_url
stages:
  - id: generate_insights
    executor: fabric_pattern
    pattern: extract_insights
    stream: true
    final_output: true
    primary_output:
      from: stdout
```

**New assets needed:**
- `data/pipelines/extract-insights.yaml`
- `data/patterns/extract_insights/system.md` — pattern for insight extraction
- `internal/pipeline/extract_insights_test.go` — definition + preflight test
- Update smoke harness

**Pattern prompt direction:**
- Main Themes (with evidence)
- Key Insights (non-obvious observations)
- Action Items (if any)
- Questions Raised
- Connections to broader topics

---

## Part 3: Documentation and Smoke Test Updates

### Docs updates
- `docs/Pipeline-Operations-and-Authoring.md` — update examples with new names
- `pipeline-vertical-slice-plan.md` — update inventory section
- `docs/plans/2026-03-06-brainstorming-session.md` — add addendum noting renames

### Smoke test updates
Update `scripts/pipelines/live_smoke.py` with all renamed + new pipeline entries:
```python
# Renamed
SmokeCase(pipeline="study-guide-technical", ...),
SmokeCase(pipeline="study-guide-conceptual", ...),
SmokeCase(pipeline="enhance-notes", ...),
SmokeCase(pipeline="conversation-notes", ...),
# New
SmokeCase(pipeline="transcript-to-notes", ...),
SmokeCase(pipeline="summarize", ...),
SmokeCase(pipeline="extract-insights", ...),
```

---

## Implementation Order

The non-breaking order is:

1. **Commit 1:** Rename `therapy-conversation-notes` → `conversation-notes`
2. **Commit 2:** Rename `note-enhancement` → `enhance-notes`
3. **Commit 3:** Rename `technical-study-guide` → `study-guide-technical`
4. **Commit 4:** Rename `nontechnical-study-guide` → `study-guide-conceptual`
5. **Commit 5:** Add `transcript-to-notes` pipeline
6. **Commit 6:** Add `summarize` pipeline
7. **Commit 7:** Add `extract-insights` pipeline
8. **Commit 8:** Update docs, smoke harness, and plan files

**After each commit:** `go test ./... && fabric --validate-pipeline data/pipelines/*.yaml`

---

## Final Pipeline Catalog

After all changes, `fabric --listpipelines` should show:

```
conversation-notes           Convert any conversation transcript to structured notes
enhance-notes                Polish and improve existing notes
extract-insights             Extract themes, insights, and action items from text
passthrough                  Emit input unchanged (utility)
study-guide-conceptual       Generate a conceptual study guide from text
study-guide-technical        Generate a technical study guide from text
summarize                    Produce a structured summary from any input
transcript-to-notes          Convert any transcript into structured notes
zoom-tech-note               Zoom transcript pipeline (parity port)
zoom-tech-note-deep-pass     Zoom pipeline with strict quality gate
```

**10 total pipelines.** Clean, discoverable, general-purpose-first.
