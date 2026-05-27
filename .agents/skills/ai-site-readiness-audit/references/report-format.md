# Report Format

The main report must feel like a scorecard, not a memo.

## Required Main Report

`01-ai-readiness-scorecard.md`

Sections:

1. `# AI Site Readiness Scorecard`
2. `## Snapshot`
3. `## Score Breakdown`
4. `## Top Fix` or `## Top Fixes`
5. `## Audit Coverage`
6. `## Audit Matrix`
7. `## Technical Appendix`

Use `## Top Fix` when there is exactly one recommended fix. Use `## Top Fixes` when there are two or more.

## Snapshot

Keep the snapshot short and business-facing. `Main issue` must be a human-readable interpretation, not raw signal/status text. `Business impact` must explain the practical consequence of the main issue.

Do not render status counts in Snapshot.
Do not add `## Result Summary` or `## Evidence Summary`.

## Top Fix / Top Fixes

Render fixes directly after Score Breakdown as a ranked table:

```markdown
| Priority | Fix | Why it matters |
|---:|---|---|
| 1 | Add more useful page copy to key pages | Gives AI systems more information to extract, cite, and use in answers. |
```

Do not render a loose `Top 3 fixes` paragraph in the snapshot.

## Audit Matrix

Place Audit Matrix directly above Technical Appendix. Do not add an Evidence Summary section.

Every finding appears in one table with exactly these columns:

```markdown
| Area | Signal | Result | Impact | Evidence | Priority |
| --- | --- | --- | --- | --- | --- |
```

Use only:

- Results: `PASS`, `PARTIAL`, `MISSING`, `UNKNOWN`
- Priorities: `HIGH`, `MEDIUM`, `LOW`, `NONE`

Do not create separate sections for passed, partial, missing, or unknown checks.

Signal labels should explain what is being checked. Prefer labels such as:

- `LLM site guide available at /llms.txt`
- `Agent instruction file available at /AGENTS.md`
- `Full LLM-readable site file available at /llms-full.txt`
- `Markdown response support through Accept header`
- `Discoverable MCP or agent-tooling reference`
- `AI crawler access rules in robots.txt`
- `Structured data describing products, offers, and site entities`
- `Semantic page structure for AI parsing`

## HTML Scorecard

Generate `01-ai-readiness-scorecard.html` alongside the Markdown report.

The HTML report should:

- Use the same audit data as Markdown and JSON.
- Be fully local static HTML with embedded CSS.
- Require no external CDN, JavaScript framework, paid API, browser automation, or PDF generation.
- Keep Top Fixes above Audit Coverage.
- Keep Audit Matrix directly above Technical Appendix.
- Use colored chips for statuses and priorities.
- Wrap long evidence text cleanly and remain readable on mobile.
