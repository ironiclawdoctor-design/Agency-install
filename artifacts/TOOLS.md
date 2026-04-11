# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → [IP_ADDRESS], user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

---

## Agency-Agents Skill Integration Notes:

*   **Purpose:** Provides access to 61 specialized AI Agents organized into 8 departments for professional tasks and multi-agent orchestration.
*   **Usage Modes:**
    *   **Single Agent:** `/openclaw skill use agency-agents --agent <agent-name> "<task description>"
        *   *Example:* `--agent frontend-developer "Create a React login page component."
    *   **Orchestrator (Recommended for complex projects):** `/openclaw skill use agency-agents --agent orchestrator "<task description>"
        *   *Example:* `--agent orchestrator "Develop a full e-commerce website."
    *   **Department-wide:** `/openclaw skill use agency-agents --department <department-name> "<task description>"
        *   *Example:* `--department engineering "Develop a full web application."
*   **Key Departments:** Engineering, Design, Marketing, Product, Project Management, Testing, Support, Specialized.
*   **Core Workflow:** User specifies task -> Agent loads expertise -> Executes task -> Provides deliverables. Orchestrator handles complex projects by decomposing tasks.
*   **Configuration:** Environment variables can set default department, QA level, retry counts, and verbosity.
*   **Best Practices:** Choose the right agent, provide clear task descriptions, iterate, and use quality assurance agents for validation.
*   **Troubleshooting:** For unexpected outputs, refine task descriptions; for inefficient multi-agent collaboration, use the orchestrator or specify agent order; for specific expertise, select specialized agents or departments.

## ACPX Force Multiplication Plugin

*   **Purpose:** Headless CLI client for Agent Control Protocol (ACP) with parallel execution, health checks, and workflow presets. Enables force multiplication via multi‑agent orchestration.
*   **Installation:** `npm install -g acpx` (global CLI) + `npm install -g proxy-acpx-x` (adapters).
*   **Skills installed:**
    *   `acpx-codex-playbook` – Persistent sessions, prompt files, shell‑based writes for Codex.
    *   `acpx-orchestrator` – Parallel execution, batch workflows, health checks.
*   **Key Commands:**
    *   `acpx discover` – List installed agents.
    *   `acpx health` – Test all agents.
    *   `acpx run <agent> "<task>"` – Run single agent.
    *   `acpx parallel tasks.txt` – Run agents in parallel from file.
    *   `acpx batch tasks.txt` – Run agents sequentially.
    *   `acpx workflow review|refactor|test|debug` – Preset workflows.
    *   `acpx json <agent> "<task>"` – JSON output.
*   **Available Agents:** pi, openclaw, codex, claude, gemini, cursor, copilot, droid, iflow, kilocode, kimi, kiro, opencode, qoder, qwen, trae.
*   **Integration with OpenClaw:** Use `sessions_spawn` to run acpx commands as subagents:
    ```javascript
    sessions_spawn(
      task="acpx health",
      label="health-check",
      runtime="subagent",
      mode="run"
    )
    ```
*   **Force Multiplication Patterns:**
    *   **Parallel execution:** `acpx parallel tasks.txt` runs multiple agents concurrently.
    *   **Batch processing:** `acpx batch tasks.txt` chains tasks sequentially.
    *   **Workflow automation:** `acpx workflow review` for code review, `acpx workflow refactor` for safe refactoring.
*   **Best Practices:**
    *   Use prompt files (`-f prompt.txt`) for long instructions.
    *   Set session mode: `acpx codex set-mode -s task full-access`.
    *   For file generation, write to `/tmp` first, validate, then move.
    *   Use local venv for dependencies; avoid global installs.
*   **Troubleshooting:**
    *   If ACP file‑edit tools fail, switch to shell/Python writes.
    *   Use `--approve-all` for non‑interactive permission approval.
    *   Check `acpx config` for agent configuration.
