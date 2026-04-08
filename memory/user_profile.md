---
name: User Profile
description: User background, project context, working preferences
type: user
---

# User Profile

Building the Clinical Intelligence Platform for Tata Memorial Centre (TMC) — a 10-agent microservices system for clinical document processing (radiology, handwritten notes, counselling audio, discharge summaries).

**Dual-track work:**
1. **Research track** (`tmc/`): Radiology NLP pipeline, improving F1 metrics, RECIST engine. Actively iterating. Do not interrupt this.
2. **Platform track**: 10-agent orchestrated system, FastAPI microservices, Next.js UI.

**Compute:** Shared GPU server "tyrone" (ssh tyrone) — RTX A6000, 100+ cores, 120GB RAM. All heavy compute goes there. Must use tmux, project-local conda envs, check GPU before use (machine.md).

**LLM budget:** Minimize LLM calls. Prefers rule-based extraction where possible (tmc has 159 rule patterns). Azure GPT-4o-mini for all text tasks.

**Stack:** Python FastAPI microservices, Next.js 14 frontend, Docker Compose, SQLite fact store, Azure OpenAI.

**Prefers:** Parallel agent dispatch for large builds, concrete file paths in responses, no time estimates.
