# Technical Checks

Run a limited static sample audit only.

## Sample Scope

- Homepage
- Up to 3 representative internal pages
- `robots.txt`
- `sitemap.xml`
- `llms.txt`
- `llms-full.txt`
- `AGENTS.md`
- `/.well-known/AGENTS.md`
- `/.well-known/agents.md`
- Common MCP discovery paths

## Representative Page Selection

Use sitemap URLs first, homepage internal links second, and common path guesses last.

For ecommerce-like sites, prioritize:

1. Product page
2. Collection/category/shop/catalog page
3. FAQ/about/contact/policy/support page

For non-ecommerce sites, prioritize:

1. Service/pricing page
2. Docs/blog/content page
3. About/FAQ/contact page

## Hard Limits

- No full-site crawl
- No JavaScript rendering
- No browser automation
- No paid APIs
- No external LLM APIs
- No database
- No auth
- No payment or deployment implementation
- No generated final contents for `llms.txt`, `llms-full.txt`, or `AGENTS.md`

## Checks

- AI bot access from `robots.txt` for common AI crawlers.
- Presence of `llms.txt`, `llms-full.txt`, and `AGENTS.md` variants.
- JSON-LD schema types on homepage and sampled pages.
- Semantic HTML landmarks and heading structure.
- Extractable content quality and internal links.
- Basic markdown extraction sample.
- `Accept: text/markdown` response behavior.
- MCP discoverability from common paths and references.
- Technical hygiene: sitemap, canonical URL, title, meta description, and HTTP accessibility.
