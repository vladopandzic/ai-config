# Global Claude Code Instructions

<!-- Shared rules for Claude and Codex live in AGENTS.md (single source). Codex reads it directly; Claude reads it through this import. -->
@AGENTS.md
@AGENTS.local.md

## Claude-specific

<!-- Only rules that Codex does not need. Everything shared belongs in AGENTS.md. -->

- The language guides listed in AGENTS.md are also linked into `%USERPROFILE%\.claude\rules\`, so they load automatically when you work with matching files. If a guide is already in your context, do not read it again.
- When the user asks you to remember something, decide where it belongs. If it applies beyond the current project, propose adding it to ai-config (AGENTS.md, or AGENTS.local.md if it is personal) instead of a project memory. Say where you saved it.
