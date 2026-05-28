# Scoring Rubric

The audit uses a 100-point score.

## Pillars

| Pillar | Points |
| --- | ---: |
| Content & Extraction Quality | 35 |
| AI Bot Access | 20 |
| Schema / Structured Data | 20 |
| Agent Readiness | 20 |
| Technical Hygiene | 5 |

## Readiness Bands

| Score | Level |
| --- | --- |
| 85-100 | AI Ready |
| 70-84 | Mostly Ready |
| 50-69 | Partial |
| 25-49 | Needs Work |
| 0-24 | Not Ready |

## Agent Readiness Subscore

| Signal | Points |
| --- | ---: |
| `llms.txt` | 5 |
| `AGENTS.md` | 5 |
| `llms-full.txt` | 3 |
| `Accept: text/markdown` | 3 |
| MCP discoverability | 2 |
| Semantic HTML | 2 |

## Priority Guidance

- Missing `llms.txt`: `HIGH`.
- Missing `AGENTS.md`: `HIGH`.
- Missing `llms-full.txt`: `MEDIUM` for most sites and `HIGH` when the site has substantial documentation, product, catalog, or policy content.
- Missing MCP discoverability: usually `LOW`.
- Missing `Accept: text/markdown`: usually `LOW` unless there is a strong reason to raise it.
- `UNKNOWN` earns no points and must not overclaim failure.

## Content Classification

- `PASS`: sampled pages provide enough meaningful readable content and structure for extraction.
- `PARTIAL`: sampled pages have readable content, but it is thin, sparse, generic, noisy, or poorly structured.
- `MISSING`: sampled pages expose effectively no extractable body content.
- `UNKNOWN`: content could not be fetched or evaluated.
