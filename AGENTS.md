# PulseGrid — Agent Coordinator

## What this is

CRM-ERP portfolio app, feeds errors to LogPulse. See docs/architecture.md, docs/stack.md.

## Rules

- Business/domain decisions not in docs/code → STOP, write to blocked.md. Do not guess.
- Technical errors (compile, missing file) → attempt self-fix first, escalate only if stuck.
- One checklist item = one commit. Do not batch multiple items into one commit.
- Do not modify LogPulse repo — HTTP calls only.
- CRM→ERP sync ~10% intentional failure rate is BY DESIGN — do not "fix" to 100% reliable.

## Docs map

- docs/architecture.md — component map
- docs/stack.md — tech stack specifics
- docs/business-logic.md — domain rules, includes [UNRESOLVED] flags
- docs/patterns.md — coding conventions (fill as they emerge)
- SPECS.md — phase/module checklist
- blocked.md — open blockers log
