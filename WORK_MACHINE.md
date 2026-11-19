# Work Machine — Mission Control

Work Machine is an independent, open-source fork of Hermes Agent by Nous Research, retaining its MIT license and Git history. Its first fork-specific addition is a native, opt-in mission ledger.

## What's actually new

The work_machine_goal tool records plans, testable acceptance criteria, step execution attempts, evidence, terminal states and an audit trail in profile-local SQLite. Every step is checkpointed in a transaction, and next is idempotent for an already-running step. A bounded attempt budget prevents silent infinite retry loops. Missions are separated by Hermes conversation_id (falling back to session_id).

**Important limitations:** This is not a new model or a fully autonomous background service. It does not run shell commands, execute tests, independently check truthfulness of evidence, or authorize privileged actions. Actual work is done through Hermes' existing tools and their approval/security policies. The stored completion state represents a recorded review, not external proof of quality. The current addition is a first step toward a Work Machine goal orchestration platform.

## Enable it

Start from this repository's normal Hermes installation instructions, using this fork's code rather than Nous Research's official installer (which installs upstream Hermes).

Then enable the bundled plugin:

    hermes plugins list
    hermes plugins enable work-machine
    hermes plugins doctor work-machine

If the plugin is installed separately, copy the plugins/work_machine directory into your own Hermes plugins directory (renaming the folder to work-machine), then enable it. The plugin adds no third-party Python dependencies and requires no new API key.

## Example interaction

Ask the agent:

    Use work_machine_goal to create a mission: audit my site, fix UI regressions,
    run tests and prepare a release. Require acceptance evidence at each step,
    with a maximum of 12 attempts. Work on one step at a time, saving the results.

The agent calls actions in this order:

1. create(title, steps, max_attempts)
2. next(mission_id) — returns a step, or the same one after interruption
3. Do real work with existing Hermes tools
4. complete_step(mission_id, step_id, evidence) or fail_step(..., reason)
5. Repeat next for remaining steps
6. finish(mission_id, review_note) only when all steps have evidence

Use status and list after a restart; cancel if the goal should be abandoned.
A failed step can be retried, but exhaustion blocks the mission without granting more attempts.

## Architecture & attribution

The original Hermes agent loop, inference providers, terminal execution, memory, plugins, Kanban, gateway, desktop apps and all original source remain in this fork. Mission Control is additive (plugins/work_machine) and does not monkey-patch the core.

Original project: https://github.com/NousResearch/hermes-agent
Original copyright: © 2025 Nous Research.
License: MIT; see LICENSE. Work Machine is a community derivative, not an official Nous Research release.

## Roadmap (not shipped yet)

- Deterministic CI/test artifact verification and an independent human-review gate.
- Web mission dashboard with progress, diffs, permissions and cost observability.
- Delegated worker dispatch through public Hermes lifecycle APIs.
- A resumable background runner with explicit user control and resource limits.
