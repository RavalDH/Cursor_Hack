# AGENTS.md

## Cursor Cloud specific instructions

As of this environment setup, the repository contains no application code — only this
file and a placeholder `README.md` (`# Cursor_Hack`). There are no dependency
manifests (no `package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`,
`Cargo.toml`, etc.), no services, no tests, and no build/lint commands to run.

Because there is nothing to install yet, the startup update script is effectively a
no-op (it only installs dependencies if a recognized manifest later appears at the
repo root). When real application code is added, revisit the update script and this
section to document how to install dependencies and how to lint, test, build, and run
each service.

Pre-installed toolchain available in this environment: Node 22 + npm 10, Python 3.12,
Go 1.22, Rust 1.83, Java 21.
