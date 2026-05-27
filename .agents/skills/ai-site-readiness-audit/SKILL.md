---
name: ai-site-readiness-audit
description: Audit a website for AI/LLM readiness and produce a scorecard showing which crawlability, schema, content extraction, AI-facing file, and agent-readiness signals are present, partial, missing, or unknown. Use when the user asks to audit a URL for AI readiness, LLM readiness, ChatGPT/Claude/Perplexity visibility, agent readiness, llms.txt readiness, AGENTS.md readiness, schema readiness, or AI crawlability. This skill is audit-only and does not generate final llms.txt, llms-full.txt, or AGENTS.md files.
---

# AI Site Readiness Audit

Use this skill to run a local-first, audit-only static sample check of a website and create a scorecard output packet.

## Workflow

1. Identify the target URL from the user request. If the scheme is missing, default to `https://`.
2. Run the bundled script:

   ```bash
   python .agents/skills/ai-site-readiness-audit/scripts/audit_site.py https://example.com
   ```

3. Confirm the packet was created under `output/{site-slug}/`.
4. Summarize the result concisely: overall score, readiness level, main issue, top fixes, and output path.

## Output Packet

The script creates exactly these files:

- `01-ai-readiness-scorecard.md`
- `01-ai-readiness-scorecard.html`
- `02-findings.json`
- `03-fix-checklist.md`
- `04-evidence-log.md`
- `05-markdown-extraction-sample.md`

## Guardrails

- Keep this skill audit-only.
- Do not generate final `llms.txt`, `llms-full.txt`, or `AGENTS.md` contents.
- Do not run a full-site crawl.
- Do not use JavaScript rendering, browser automation, paid APIs, external LLM APIs, databases, auth, hosted app scaffolds, payment integration, or deployment flows.
- Mark checks as `UNKNOWN` when requests fail or static evidence is inconclusive.
- Keep the final response short and point the user to the created scorecard.

## References

Load these only when needed:

- `references/scoring-rubric.md` for scoring and readiness bands.
- `references/status-definitions.md` for status and priority labels.
- `references/technical-checks.md` for the V0 checks and hard limits.
- `references/report-format.md` for the scorecard packet shape.
