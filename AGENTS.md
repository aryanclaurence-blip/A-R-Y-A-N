# Repository Agent Instructions

These instructions are mandatory for every AI coding agent and human-assisted automation working in this repository. Read this file before modifying code.

## Core Rule

**ONE PROBLEM = ONE BRANCH = ONE TESTED SOLUTION = ONE MERGE = ONE RELEASE DECISION**

`main` is always production/release-ready. Never use `main` as a development branch.

## Agent Startup Procedure

Before starting any work, run and inspect:

```bash
git status
git branch --show-current
git fetch origin
```

If there is no `origin` remote, report that synchronization and PR/release publication are blocked until a remote is configured. Do not invent a remote.

If currently on `main`, do **not** begin development directly on `main`. Create an appropriate branch from the latest synchronized `main`:

- `feature/<feature-name>` for new functionality
- `fix/<problem-name>` for normal bug fixes
- `hotfix/<problem-name>` for urgent production problems

## Main Branch Rules

- `main` is production/release-ready.
- Never directly develop on `main`.
- Never make experimental changes directly on `main`.
- Never commit unfinished code to `main`.
- Never push untested code to `main`.
- Before starting development, synchronize with the latest `main`.
- Do not merge to `main` until the change has been implemented, tested, reviewed, and approved for release readiness.

## Allowed Branch Types

Use only these branch prefixes:

```text
feature/
fix/
hotfix/
```

Examples:

```text
feature/workset-manager
feature/parameter-mapper
feature/color-splasher

fix/linked-room-selection
fix/parameter-validation
fix/ui-crash

hotfix/revit-2026-crash
```

Do **not** introduce unnecessary long-lived branches such as:

```text
develop
release/*
integration
staging
experimental
```

unless there is a documented technical requirement and explicit repository owner approval.

## Feature Workflow

For new functionality:

```text
main
 ↓
feature/<feature-name>
 ↓
implement
 ↓
test
 ↓
review
 ↓
merge to main
 ↓
release decision
```

The actual development branch must be created from the latest `main`.

## Bug Fix Workflow

For normal bugs:

```text
main
 ↓
fix/<problem-name>
 ↓
implement
 ↓
test
 ↓
review
 ↓
merge to main
 ↓
patch release decision
```

## Hotfix Workflow

For urgent production problems:

```text
main
 ↓
hotfix/<problem-name>
 ↓
implement
 ↓
test
 ↓
review
 ↓
merge to main
 ↓
patch release decision
```

## Semantic Versioning

Use Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

Examples:

```text
1.0.0
1.0.1
1.1.0
2.0.0
```

Version bump rules:

- **PATCH**: bug fixes only, e.g. `1.0.0` → `1.0.1`.
- **MINOR**: backward-compatible new functionality, e.g. `1.0.1` → `1.1.0`.
- **MAJOR**: breaking changes or major architectural changes, e.g. `1.1.0` → `2.0.0`.

Never randomly change the version number.

## Release Process

A change is **not** released merely because it works locally.

Mandatory release flow:

```text
PROBLEM / FEATURE
        ↓
CREATE BRANCH
        ↓
IMPLEMENT
        ↓
TEST
        ↓
FIX FAILURES
        ↓
RETEST
        ↓
COMMIT
        ↓
PUSH BRANCH
        ↓
REVIEW
        ↓
MERGE INTO MAIN
        ↓
UPDATE VERSION
        ↓
CREATE GIT TAG
        ↓
CREATE GITHUB RELEASE
```

Do **not** automatically release every change. After solving a problem, classify the change:

```text
BUG FIX       → PATCH
NEW FEATURE   → MINOR
BREAKING      → MAJOR
```

Ask for, or require, the appropriate release decision if the workflow does not explicitly authorize automatic releases. Never silently publish a major or breaking release.

## Commit Rules

Use meaningful commits.

Bad commit messages:

```text
update
changes
fix
test
done
```

Good commit messages:

```text
Fix linked room parameter validation
Add multiple target mapping queue
Improve Revit 2026 selection handling
Prevent transaction failure on read-only parameters
```

Do not create meaningless commits just to make progress appear.

## Testing Requirement

Before merging any branch into `main`, verify the actual functionality.

For Revit tools, where applicable, test:

- Normal workflow
- Empty selection
- Invalid selection
- Cancel / Esc
- Multiple selections
- Linked models
- Missing parameters
- Read-only parameters
- Wrong parameter types
- Transaction failures
- UI behavior
- Revit 2026 compatibility
- Unexpected user input
- Error handling
- Repeated execution
- Existing functionality/regression

Do not claim something is tested if it was not actually tested.

If testing cannot be performed because Revit is unavailable, explicitly state:

```text
NOT TESTED — REVIT ENVIRONMENT UNAVAILABLE
```

Do not falsely report success.

## Preserve Existing Functionality

Before modifying an existing feature:

1. Understand the current implementation.
2. Identify dependencies.
3. Preserve existing behavior unless the task explicitly requires changing it.
4. Test the affected functionality.
5. Test related functionality for regressions.

Do not rewrite unrelated code simply because it can be improved.

## Release Tagging

After a successful merge into `main`, create an annotated Git tag:

```bash
git tag -a v1.1.0 -m "Version 1.1.0 - Add Multiple Mapping Queue"
git push origin v1.1.0
```

Tags must follow:

```text
vMAJOR.MINOR.PATCH
```

Examples:

```text
v1.0.0
v1.0.1
v1.1.0
v2.0.0
```

Never overwrite an existing release tag.

## Release History

Maintain a clear release history. Each release should identify:

- Version
- Date
- New features
- Bug fixes
- Important changes
- Breaking changes, if any
- Testing status

If the repository already contains a changelog or release-notes system, inspect and use the existing system rather than creating a duplicate.

## Do Not Delete or Rewrite Shared History

Never rewrite shared branch history.

Do not use:

```bash
git push --force
```

on `main` or release branches.

Do not delete tags. Do not modify an already-published release to hide mistakes. If a release has an error, create a new patch version.

Example: if `v1.1.0` has a release problem, create `v1.1.1`. Do **not** replace `v1.1.0`.

## Final Branch Model

```text
                         ┌── feature/*
                         │
                         ├── fix/*
                         │
MAIN ────────────────────┤
                         └── hotfix/*
                                  │
                                  ▼
                              TESTING
                                  │
                                  ▼
                                MERGE
                                  │
                                  ▼
                                MAIN
                                  │
                                  ▼
                             VERSION BUMP
                                  │
                                  ▼
                              GIT TAG
                                  │
                                  ▼
                         GITHUB RELEASE
```

The core policy is:

```text
main = stable release
feature = new functionality
fix = normal bug fix
hotfix = urgent production fix
```

## Pull Requests and Publishing

- Do not push branches, create GitHub releases, delete branches, or publish tags unless explicitly asked.
- Do not create a pull request unless the task explicitly requests PR creation or repository automation requires it.
- If a remote or authentication is missing, report the blocker with exact commands/output.
