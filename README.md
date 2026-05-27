# AI Site Readiness Audit

A Codex Skill that audits a website for AI-readiness and generates a business-facing scorecard showing whether AI systems can crawl, understand, extract, cite, and interact with the site.

## What It Does

- Checks whether AI crawlers appear able to access the site.
- Checks for AI-facing files like `llms.txt`, `llms-full.txt`, and `AGENTS.md`.
- Checks structured data and JSON-LD.
- Checks semantic HTML and extractable content.
- Checks markdown-friendly access signals.
- Checks basic MCP and agent-tooling discoverability.
- Generates a polished HTML report, markdown scorecard, JSON findings, fix checklist, evidence log, and markdown extraction sample.

## Why It Matters

AI search, LLM answers, RAG systems, and future agents need clean signals to understand a website. This skill shows what is already working, what is unclear, and what should be fixed first.

## Example Output

```text
output/{site-slug}/
  01-ai-readiness-scorecard.md
  01-ai-readiness-scorecard.html
  02-findings.json
  03-fix-checklist.md
  04-evidence-log.md
  05-markdown-extraction-sample.md
```

- HTML is the polished business-facing report.
- Markdown is the simple readable scorecard.
- JSON is for future automation or integrations.
- Checklist is the action list.
- Evidence log shows what was checked.

## How To Use

Run the audit script directly:

```bash
python .agents/skills/ai-site-readiness-audit/scripts/audit_site.py https://example.com --out output/example
```

Or use it from Codex:

```text
Use $ai-site-readiness-audit to audit https://example.com and create the AI readiness scorecard.
```

## What The Report Includes

- Snapshot
- Score Breakdown
- Top Fixes
- Audit Coverage
- Audit Matrix
- Technical Appendix

## What This Does Not Do

- Does not perform a full-site crawl.
- Does not render JavaScript.
- Does not use paid APIs.
- Does not require a database or hosted service.
- Does not generate final implementation files like `llms.txt`, `llms-full.txt`, or `AGENTS.md`.
- Does not export PDF yet.
- Does not include x402 or NLWeb checks.

## Skill Location

The skill lives at:

```text
.agents/skills/ai-site-readiness-audit/
```

## Requirements

- Python 3
- Standard-library-only for the core audit
- No API keys required

## Acknowledgements

This project was inspired in part by Context CLI, an open-source MIT-licensed project for auditing URL readiness for LLMs and AI agents.

AI Site Readiness Audit is an independent Codex Skill and is not affiliated with or endorsed by Context CLI.
