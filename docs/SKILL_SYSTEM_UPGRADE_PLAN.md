# Plan: Rich Skill System Upgrade (Claude-Inspired)

## Objective
Upgrade the Jarvis Agent skill system to support rich, documentation-heavy skill definitions (Markdown + Frontmatter) similar to the [Claude Skill Creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) approach. This moves beyond simple Python snippets to comprehensive "Skill Packages" that include instructions, usage context, dependency checks, and troubleshooting guides.

## 1. New Skill Format (`SKILL.md`)

Adopt a structured Markdown format with YAML frontmatter.

```markdown
---
name: skill-name-kebab-case
description: Brief summary of what the skill does.
version: 1.0.0
tags: [tag1, tag2]
allowed-tools: [python, bash, ...options]
dependencies: [pandas, trafilatura, ...]
---

# Skill Name

## Description
Detailed explanation of the skill's purpose and capabilities.

## Usage
When and how to use this skill.

## Dependencies & Setup
How to install required tools (if any).

## Code / Implementation

### Python
```python
def main():
    ...
```

### Bash (Optional)
```bash
# command examples
```

## Troubleshooting
Common errors and fixes.
```

## 2. Architecture Changes

### A. Skill Library (`app/core/skills.py`)
**Goal:** Make the File System the "Source of Truth" and ChromaDB the "Search Index".

1.  **Markdown Parser Upgrade:**
    *   Implement `python-frontmatter` (or manual parsing) to extract YAML metadata.
    *   Store the *entire* markdown content in ChromaDB `documents` for better semantic retrieval of "instructions" and "usage context", not just the code.
    *   Extract `dependencies` from frontmatter to auto-install packages during execution.

2.  **File Persistence:**
    *   Update `save_skill()` to write/update the `.md` file in `.jarvis/skills/` instead of just updating the DB.
    *   Ensure filename matches `name` in frontmatter.

### B. Skills Engine (`app/core/skills_engine.py`)
**Goal:** Add a "Documentation Phase" to the approval pipeline.

1.  **New Node: `SkillDocumenter`**:
    *   **Input:** Verified Code + User Description.
    *   **Process:** Uses a specialized LLM prompt (The "Skill Creator") to generate the rich Markdown documentation (Usage, Troubleshooting, Frontmatter).
    *   **Output:** Complete `SKILL.md` content.

2.  **Pipeline Update:**
    *   *Current:* Lint -> Test -> Refine -> Save Code.
    *   *New:* Lint -> Test -> Refine -> **Document** -> **Save Markdown**.

### C. Execution Engine (`app/execution/sandbox.py`)
**Goal:** Support broader execution types.

1.  **Dependency Handling:**
    *   Read `dependencies` from skill metadata and ensure they are installed in the sandbox before execution.
2.  **Bash Support (Optional):**
    *   If a skill is marked as `type: bash` or `allowed-tools: [bash]`, execute the block via shell instead of Python repl.

## 3. Implementation Steps

### Phase 1: Core Library Update
1.  Modify `SkillLibrary._load_skills_from_markdown` to parse YAML frontmatter.
2.  Modify `SkillLibrary.save_skill` to write `.md` files to disk.

### Phase 2: Documentation Generator
1.  Create `app/prompts/skill_documentation.py` with a prompt designed to generate the Claude-style format.
2.  Create `app/core/nodes/documentation_node.py` to run this generation.

### Phase 3: Pipeline Integration
1.  Update `JobRunner.run_verification_job` to include the documentation step after successful verification but before saving.

### Phase 4: CLI/UI Updates
1.  Update `jarvis-ui` to render the Markdown description (Usage, etc.) instead of just showing code.

## 4. Example "Skill Creator" Prompt Logic

```text
You are an expert technical writer and developer.
Given the following working Python code and user description, create a high-quality SKILL.md document.

Format:
- YAML Frontmatter (name, description, dependencies)
- Section: When to Use
- Section: How to Use
- Section: Code (The provided code)
- Section: Error Handling

Code: {code}
Description: {description}
```

```