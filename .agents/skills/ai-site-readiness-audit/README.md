# AI Site Readiness Audit Skill

Local Codex Skill for auditing practical AI/LLM readiness of a website.

It answers:

> Can AI systems and future agents crawl, understand, extract, cite, and interact with this website?

The skill is diagnostic only. It creates a scorecard-style audit packet and does not generate final `llms.txt`, `llms-full.txt`, or `AGENTS.md` implementation files.

## Codex Usage

Use this prompt:

```text
Use $ai-site-readiness-audit to audit https://YOUR-DOMAIN.com and create the AI readiness scorecard.
```

## Direct Script Usage

```bash
python .agents/skills/ai-site-readiness-audit/scripts/audit_site.py https://YOUR-DOMAIN.com --out output/your-domain
```

If `--out` is omitted, output is written to:

```text
output/{site-slug}/
```

## Output Packet

Each audit creates exactly:

```text
01-ai-readiness-scorecard.md
01-ai-readiness-scorecard.html
02-findings.json
03-fix-checklist.md
04-evidence-log.md
05-markdown-extraction-sample.md
```

## Scope

The skill runs a limited static sample audit:

- Homepage
- Up to 3 representative internal pages
- `robots.txt`
- `sitemap.xml`
- `llms.txt`
- `llms-full.txt`
- `AGENTS.md` and common variants
- Common MCP discovery paths

Hard limits:

- No full-site crawl
- No JavaScript rendering
- No browser automation
- No paid APIs
- No external LLM APIs
- No database
- No auth
- No hosted app generation

## Dependencies

The script uses the Python standard library only.
