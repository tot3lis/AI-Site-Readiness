#!/usr/bin/env python3
"""Limited static AI site readiness audit.

Creates a scorecard-style output packet for practical AI/LLM crawl,
extraction, citation, and agent-readiness signals.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


USER_AGENT = "CodexAISiteReadinessAudit/0.1 (+local-static-audit)"
TIMEOUT_SECONDS = 12
MAX_BODY_BYTES = 2_000_000

AI_BOTS = [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Grok",
    "DeepSeek-AI",
    "Amazonbot",
    "Meta-ExternalAgent",
    "cohere-ai",
    "AI2Bot",
    "ByteSpider",
]

SCHEMA_TYPES = {
    "Product",
    "Offer",
    "Organization",
    "WebSite",
    "BreadcrumbList",
    "Article",
    "FAQPage",
    "HowTo",
    "Recipe",
    "LocalBusiness",
    "AggregateRating",
    "Review",
    "Brand",
}

ECOMMERCE_PATTERNS = [
    "/product",
    "/products",
    "/collection",
    "/collections",
    "/category",
    "/shop",
    "/catalog",
    "/store",
]

GENERAL_PATTERNS = [
    "/services",
    "/pricing",
    "/docs",
    "/blog",
    "/about",
    "/faq",
    "/contact",
]

AGENT_PATHS = [
    "/AGENTS.md",
    "/agents.md",
    "/.well-known/AGENTS.md",
    "/.well-known/agents.md",
    "/docs/AGENTS.md",
]

MCP_PATHS = [
    "/.well-known/mcp.json",
    "/mcp",
    "/mcp.json",
    "/api/mcp",
]


@dataclass
class FetchResult:
    url: str
    status: int | None
    content_type: str
    text: str
    error: str | None = None
    final_url: str | None = None
    headers_sent: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and not self.error

    @property
    def nonempty(self) -> bool:
        return bool(self.text.strip())


@dataclass
class PageInfo:
    url: str
    fetch: FetchResult
    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    text: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)
    landmarks: dict[str, int] = field(default_factory=dict)
    aria_count: int = 0
    role_count: int = 0
    markdown: str = ""


class AuditHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.meta_description = ""
        self.canonical = ""
        self.links: list[str] = []
        self.headings: list[str] = []
        self.jsonld_raw: list[str] = []
        self.landmarks: dict[str, int] = {
            "header": 0,
            "nav": 0,
            "main": 0,
            "article": 0,
            "section": 0,
            "footer": 0,
            "h1": 0,
            "h2": 0,
            "h3": 0,
        }
        self.aria_count = 0
        self.role_count = 0
        self._capture_title = False
        self._capture_heading: str | None = None
        self._capture_jsonld = False
        self._skip_depth = 0
        self._text_parts: list[str] = []
        self._title_parts: list[str] = []
        self._heading_parts: list[str] = []
        self._jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
                self._capture_jsonld = True
                self._jsonld_parts = []
            else:
                self._skip_depth += 1
            return
        if tag in self.landmarks:
            self.landmarks[tag] += 1
        if any(k.startswith("aria-") for k in attrs_dict):
            self.aria_count += 1
        if "role" in attrs_dict:
            self.role_count += 1
        if tag == "title":
            self._capture_title = True
            self._title_parts = []
        elif tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_description = clean_space(attrs_dict.get("content", ""))
        elif tag == "link" and attrs_dict.get("rel", "").lower() == "canonical":
            self.canonical = urllib.parse.urljoin(self.base_url, attrs_dict.get("href", ""))
        elif tag == "a" and attrs_dict.get("href"):
            self.links.append(urllib.parse.urljoin(self.base_url, attrs_dict["href"]))
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = tag
            self._heading_parts = []
        elif tag in {"p", "div", "section", "article", "main", "li", "br"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture_jsonld and tag == "script":
            raw = "".join(self._jsonld_parts).strip()
            if raw:
                self.jsonld_raw.append(raw)
            self._capture_jsonld = False
            return
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title" and self._capture_title:
            self.title = clean_space("".join(self._title_parts))
            self._capture_title = False
        elif self._capture_heading and tag == self._capture_heading:
            heading = clean_space("".join(self._heading_parts))
            if heading:
                self.headings.append(heading)
            self._capture_heading = None
        elif tag in {"p", "div", "section", "article", "main", "li"}:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._capture_jsonld:
            self._jsonld_parts.append(data)
            return
        if self._skip_depth:
            return
        if self._capture_title:
            self._title_parts.append(data)
        if self._capture_heading:
            self._heading_parts.append(data)
        self._text_parts.append(data)

    def text(self) -> str:
        return clean_space("\n".join(self._text_parts))


def clean_space(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()


def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("URL is required")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Unsupported URL: {raw}")
    path = parsed.path or "/"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def same_site(url: str, root: str) -> bool:
    return urllib.parse.urlparse(url).netloc.lower() == urllib.parse.urlparse(root).netloc.lower()


def site_slug(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    slug = re.sub(r"^www\.", "", host)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "site"


def url_for(root: str, path: str) -> str:
    parsed = urllib.parse.urlparse(root)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def fetch(url: str, accept: str = "text/html,*/*;q=0.8") -> FetchResult:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BODY_BYTES)
            content_type = response.headers.get("Content-Type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return FetchResult(
                url=url,
                status=response.status,
                content_type=content_type,
                text=text,
                final_url=response.geturl(),
                headers_sent=headers,
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
        charset = exc.headers.get_content_charset() or "utf-8"
        return FetchResult(
            url=url,
            status=exc.code,
            content_type=exc.headers.get("Content-Type", ""),
            text=raw.decode(charset, errors="replace"),
            error=None,
            final_url=exc.geturl(),
            headers_sent=headers,
        )
    except Exception as exc:
        return FetchResult(
            url=url,
            status=None,
            content_type="",
            text="",
            error=f"{type(exc).__name__}: {exc}",
            headers_sent=headers,
        )


def parse_jsonld_types(raw_blocks: list[str]) -> list[str]:
    found: set[str] = set()

    def visit(obj: Any) -> None:
        if isinstance(obj, dict):
            value = obj.get("@type")
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str):
                    short = item.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                    if short in SCHEMA_TYPES:
                        found.add(short)
            for child in obj.values():
                visit(child)
        elif isinstance(obj, list):
            for child in obj:
                visit(child)

    for raw in raw_blocks:
        try:
            visit(json.loads(raw))
        except json.JSONDecodeError:
            for match in re.findall(r'"@type"\s*:\s*"([^"]+)"', raw):
                short = match.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                if short in SCHEMA_TYPES:
                    found.add(short)
    return sorted(found)


def parse_page(result: FetchResult) -> PageInfo:
    parser = AuditHTMLParser(result.final_url or result.url)
    if result.text:
        parser.feed(result.text)
    text = parser.text()
    headings = parser.headings[:30]
    markdown = make_markdown(parser.title, headings, text)
    return PageInfo(
        url=result.final_url or result.url,
        fetch=result,
        title=parser.title,
        meta_description=parser.meta_description,
        canonical=parser.canonical,
        text=text,
        headings=headings,
        links=dedupe(parser.links),
        jsonld_types=parse_jsonld_types(parser.jsonld_raw),
        landmarks=parser.landmarks,
        aria_count=parser.aria_count,
        role_count=parser.role_count,
        markdown=markdown,
    )


def make_markdown(title: str, headings: list[str], text: str) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
    for heading in headings[:8]:
        if heading and heading not in lines:
            lines.append(f"## {heading}")
    body = clean_space(text)
    if body:
        paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
        seen: set[str] = set()
        for para in paragraphs:
            if para in seen or len(para) < 25:
                continue
            seen.add(para)
            lines.append(para)
            if sum(len(x) for x in lines) > 7000:
                break
    return "\n\n".join(lines).strip() + "\n"


def dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def load_sitemap_urls(root: str, evidence: list[FetchResult]) -> tuple[FetchResult, list[str]]:
    sitemap = fetch(url_for(root, "/sitemap.xml"), accept="application/xml,text/xml,*/*;q=0.8")
    evidence.append(sitemap)
    if not sitemap.ok or not sitemap.text.strip():
        return sitemap, []
    urls: list[str] = []
    try:
        xml_root = ET.fromstring(sitemap.text)
        for loc in xml_root.findall(".//{*}loc"):
            if loc.text:
                candidate = loc.text.strip()
                if same_site(candidate, root):
                    urls.append(candidate)
    except ET.ParseError:
        urls = re.findall(r"<loc>\s*([^<]+)\s*</loc>", sitemap.text, flags=re.I)
        urls = [u for u in urls if same_site(u, root)]
    return sitemap, dedupe(urls)


def classify_site(urls: list[str], homepage: PageInfo) -> bool:
    joined = "\n".join(urls[:200] + homepage.links[:200]).lower()
    text = (homepage.text + " " + " ".join(homepage.jsonld_types)).lower()
    commerce_signals = ["product", "products", "shop", "cart", "catalog", "collection", "price", "add to cart"]
    return any(signal in joined or signal in text for signal in commerce_signals)


def select_representative_urls(root: str, homepage: PageInfo, sitemap_urls: list[str], is_ecommerce: bool) -> list[str]:
    candidates = [u for u in sitemap_urls if same_site(u, root)]
    candidates.extend([u for u in homepage.links if same_site(u, root)])
    patterns = ECOMMERCE_PATTERNS + ["/faq", "/about", "/contact", "/policy", "/support"] if is_ecommerce else GENERAL_PATTERNS
    candidates.extend(url_for(root, path) for path in patterns)
    root_norm = root.rstrip("/")

    buckets: list[list[str]] = []
    if is_ecommerce:
        buckets = [
            ["/product", "/products"],
            ["/collection", "/collections", "/category", "/shop", "/catalog", "/store"],
            ["/faq", "/about", "/contact", "/policy", "/support"],
        ]
    else:
        buckets = [
            ["/services", "/pricing"],
            ["/docs", "/blog", "/article", "/guide", "/resources"],
            ["/about", "/faq", "/contact"],
        ]

    selected: list[str] = []
    for bucket in buckets:
        for candidate in dedupe(candidates):
            parsed = urllib.parse.urlparse(candidate)
            path = parsed.path.lower().rstrip("/")
            if candidate.rstrip("/") == root_norm:
                continue
            if any(path.startswith(pattern) for pattern in bucket):
                selected.append(strip_fragment(candidate))
                break
    for candidate in dedupe(candidates):
        if len(selected) >= 3:
            break
        clean = strip_fragment(candidate)
        if clean.rstrip("/") != root_norm and clean not in selected:
            selected.append(clean)
    return selected[:3]


def strip_fragment(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def analyze_robots(result: FetchResult) -> tuple[str, float, list[str], str]:
    if result.error:
        return "UNKNOWN", 0.0, [f"/robots.txt request failed: {result.error}"], "Could not verify AI bot access."
    if result.status == 404:
        return "UNKNOWN", 0.0, ["/robots.txt returned 404; no explicit AI bot directives found"], "AI crawler access is not explicitly documented."
    if not result.ok:
        return "UNKNOWN", 0.0, [f"/robots.txt returned HTTP {result.status}"], "Could not verify AI bot access."
    rules = parse_robots(result.text)
    allowed = 0
    blocked = 0
    absent = 0
    evidence: list[str] = []
    for bot in AI_BOTS:
        state = rules.get(bot.lower())
        if state == "blocked":
            blocked += 1
            evidence.append(f"{bot}: blocked")
        elif state == "allowed":
            allowed += 1
            evidence.append(f"{bot}: allowed")
        else:
            absent += 1
    if blocked and allowed:
        return "PARTIAL", max(0.25, allowed / len(AI_BOTS)), evidence[:8], "Some AI bots appear blocked while others are allowed."
    if blocked:
        return "MISSING", 0.0, evidence[:8], "AI systems may be blocked from crawling useful content."
    if allowed:
        return "PASS", 1.0, evidence[:8], "AI bot access is explicitly allowed for at least some crawlers."
    return "PARTIAL", 0.45, [f"robots.txt found, but {absent} tracked AI bot agents had no explicit directive"], "AI crawler access is not clearly documented."


def parse_robots(text: str) -> dict[str, str]:
    states: dict[str, str] = {}
    current_agents: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key_l = key.lower()
        value_l = value.lower()
        if key_l == "user-agent":
            current_agents = [value_l]
        elif key_l in {"allow", "disallow"} and current_agents:
            for agent in current_agents:
                if agent in {bot.lower() for bot in AI_BOTS}:
                    if key_l == "disallow" and value_l in {"", "/"}:
                        states[agent] = "blocked" if value_l == "/" else "allowed"
                    elif key_l == "allow" and value_l in {"", "/"}:
                        states[agent] = "allowed"
                    elif key_l == "disallow" and value_l:
                        states.setdefault(agent, "partial")
    return states


def file_presence(root: str, path: str, evidence: list[FetchResult]) -> FetchResult:
    result = fetch(url_for(root, path), accept="text/plain,text/markdown,*/*;q=0.8")
    evidence.append(result)
    return result


def presence_status(result: FetchResult, label: str) -> tuple[str, list[str]]:
    if result.error:
        return "UNKNOWN", [f"{label} request failed: {result.error}"]
    if result.status == 404:
        return "MISSING", [f"{label} returned 404"]
    if result.ok and result.nonempty:
        return "PASS", [f"{label} returned HTTP {result.status} and non-empty content"]
    if result.ok:
        return "MISSING", [f"{label} returned HTTP {result.status} but was empty"]
    return "UNKNOWN", [f"{label} returned HTTP {result.status}"]


def evaluate_schema(pages: list[PageInfo], is_ecommerce: bool) -> tuple[str, int, list[str], str, str]:
    if not pages:
        return "UNKNOWN", 0, ["No pages could be fetched for JSON-LD analysis"], "Could not verify structured data from the static sample.", "Re-run when sampled pages are accessible."
    types = sorted({t for page in pages for t in page.jsonld_types})
    if not types:
        return "MISSING", 0, ["No JSON-LD schema types detected in sampled pages"], "AI systems have less structured context for extraction and citation.", "Add JSON-LD for organization, pages, and key entities."
    score = 8
    if "Organization" in types or "LocalBusiness" in types:
        score += 4
    if "WebSite" in types:
        score += 2
    if "BreadcrumbList" in types:
        score += 2
    if is_ecommerce:
        ecommerce_types = {"Product", "Offer", "Brand", "AggregateRating", "Review"}
        score += min(4, len(ecommerce_types.intersection(types)))
        if {"Product", "Offer"}.issubset(types):
            status = "PASS"
        elif "Product" in types:
            status = "PARTIAL"
        else:
            status = "PARTIAL"
    else:
        content_types = {"Article", "FAQPage", "HowTo", "Recipe"}
        score += min(4, len(content_types.intersection(types)))
        status = "PASS" if score >= 15 else "PARTIAL"
    score = min(20, score)
    evidence = [f"Detected JSON-LD types: {', '.join(types)}"]
    return status, score, evidence, "Structured data helps AI systems identify entities, offers, and citeable page meaning.", "Improve JSON-LD coverage on important sampled page types."


def evaluate_semantic_html(pages: list[PageInfo]) -> tuple[str, float, list[str]]:
    if not pages:
        return "UNKNOWN", 0.0, ["No pages were available for semantic HTML checks"]
    total = 0
    max_total = len(pages) * 8
    evidence: list[str] = []
    for page in pages:
        page_score = 0
        for tag in ["header", "nav", "main", "footer"]:
            if page.landmarks.get(tag, 0):
                page_score += 1
        if page.landmarks.get("h1", 0):
            page_score += 1
        if page.landmarks.get("h2", 0) or page.landmarks.get("h3", 0):
            page_score += 1
        if page.aria_count:
            page_score += 1
        if page.role_count or page.landmarks.get("article", 0) or page.landmarks.get("section", 0):
            page_score += 1
        total += page_score
        evidence.append(f"{page.url}: semantic score {page_score}/8")
    ratio = total / max_total if max_total else 0
    if ratio >= 0.72:
        return "PASS", ratio, evidence
    if ratio >= 0.35:
        return "PARTIAL", ratio, evidence
    return "MISSING", ratio, evidence


def evaluate_content(pages: list[PageInfo]) -> tuple[str, int, list[str], str, str]:
    if not pages:
        return "UNKNOWN", 0, ["No pages could be fetched for content extraction analysis"], "Could not verify whether AI systems can extract useful page content.", "Re-run when pages are accessible."
    scores: list[int] = []
    word_counts: list[int] = []
    evidence: list[str] = []
    for page in pages:
        words = len(re.findall(r"\w+", page.text))
        word_counts.append(words)
        heading_count = len(page.headings)
        link_count = len([u for u in page.links if same_site(u, pages[0].url)])
        page_score = 0
        if words >= 700:
            page_score += 12
        elif words >= 300:
            page_score += 9
        elif words >= 120:
            page_score += 5
        if heading_count >= 4:
            page_score += 8
        elif heading_count >= 2:
            page_score += 5
        elif heading_count >= 1:
            page_score += 2
        if link_count >= 8:
            page_score += 5
        elif link_count >= 3:
            page_score += 3
        if any(term in page.text.lower() for term in ["faq", "question", "answer", "pricing", "features", "specifications", "support"]):
            page_score += 4
        if page.jsonld_types:
            page_score += 3
        scores.append(min(35, page_score))
        evidence.append(f"{page.url}: {words} words, {heading_count} headings, {link_count} internal links")
    score = round(sum(scores) / len(scores))
    if score >= 26:
        status = "PASS"
    elif max(word_counts, default=0) < 20:
        status = "MISSING"
    else:
        status = "PARTIAL"
    return status, score, evidence, "AI systems can access the pages, but may not have enough useful page copy to answer questions, cite pages, or recommend products confidently.", "Add more useful page copy to key pages."


def evaluate_accept_markdown(homepage_url: str, evidence: list[FetchResult]) -> tuple[str, int, list[str]]:
    result = fetch(homepage_url, accept="text/markdown")
    evidence.append(result)
    if result.error:
        return "UNKNOWN", 0, [f"Accept: text/markdown request failed: {result.error}"]
    content_type = result.content_type.lower()
    body = result.text[:500].lstrip()
    if result.ok and ("markdown" in content_type or body.startswith("# ") or "\n# " in body[:200]):
        return "PASS", 3, [f"Returned markdown-like response with Content-Type: {result.content_type or 'unknown'}"]
    if result.ok:
        return "MISSING", 0, [f"Returned normal response with Content-Type: {result.content_type or 'unknown'}"]
    return "UNKNOWN", 0, [f"Returned HTTP {result.status}"]


def evaluate_mcp(root: str, homepage: PageInfo, robots: FetchResult, llms: FetchResult | None, agents: FetchResult | None, evidence: list[FetchResult]) -> tuple[str, int, list[str]]:
    found_path: str | None = None
    partial_refs: list[str] = []
    path_results: list[FetchResult] = []
    for path in MCP_PATHS:
        result = fetch(url_for(root, path), accept="application/json,text/plain,*/*;q=0.8")
        evidence.append(result)
        path_results.append(result)
        if result.ok and result.nonempty:
            found_path = path
            break
    combined_refs = "\n".join([
        homepage.fetch.text[:50_000],
        robots.text[:20_000],
        llms.text[:20_000] if llms else "",
        agents.text[:20_000] if agents else "",
    ]).lower()
    if 'rel="mcp"' in combined_refs or "rel='mcp'" in combined_refs or "mcp.json" in combined_refs or "/mcp" in combined_refs:
        partial_refs.append("MCP reference text found in checked resources")
    if found_path:
        return "PASS", 2, [f"{found_path} returned HTTP 200 with non-empty content"]
    if partial_refs:
        return "PARTIAL", 1, partial_refs
    if path_results and all(result.error for result in path_results):
        return "UNKNOWN", 0, [f"Common MCP discovery path requests failed: {path_results[0].error}"]
    return "MISSING", 0, ["No common MCP discovery path or reference was found"]


def technical_hygiene(homepage: PageInfo, sitemap: FetchResult) -> tuple[str, int, list[str], str]:
    score = 0
    evidence: list[str] = []
    if homepage.fetch.ok:
        score += 1
        evidence.append(f"Homepage returned HTTP {homepage.fetch.status}")
    else:
        evidence.append(f"Homepage status: {homepage.fetch.status or homepage.fetch.error}")
    if sitemap.ok and sitemap.nonempty:
        score += 1
        evidence.append("/sitemap.xml found")
    else:
        evidence.append("/sitemap.xml not verified")
    if homepage.canonical:
        score += 1
        evidence.append(f"Canonical found: {homepage.canonical}")
    else:
        evidence.append("Canonical URL not found on homepage")
    if homepage.title:
        score += 1
        evidence.append(f"Title found: {homepage.title[:80]}")
    else:
        evidence.append("Title tag not found on homepage")
    if homepage.meta_description:
        score += 1
        evidence.append("Meta description found on homepage")
    else:
        evidence.append("Meta description not found on homepage")
    if score >= 4:
        status = "PASS"
    elif score >= 2:
        status = "PARTIAL"
    else:
        status = "MISSING"
    return status, score, evidence, "Basic technical metadata supports indexing and citation context."


def finding(area: str, signal: str, status: str, score: int, max_score: int, impact: str, evidence: list[str], priority: str, action: str) -> dict[str, Any]:
    return {
        "area": area,
        "signal": signal,
        "status": status,
        "score": score,
        "maxScore": max_score,
        "impact": impact,
        "evidence": evidence,
        "priority": priority,
        "recommendedAction": action,
    }


def status_points(status: str, max_score: int, partial_points: int | None = None) -> int:
    if status == "PASS":
        return max_score
    if status == "PARTIAL":
        return partial_points if partial_points is not None else max(1, max_score // 2)
    return 0


def readiness_level(score: int) -> str:
    if score >= 85:
        return "AI Ready"
    if score >= 70:
        return "Mostly Ready"
    if score >= 50:
        return "Partial"
    if score >= 25:
        return "Needs Work"
    return "Not Ready"


def priority_sort(item: dict[str, Any]) -> tuple[int, int]:
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
    return (order.get(item["priority"], 9), -int(item.get("maxScore", 0)))


def get_finding(findings: list[dict[str, Any]], signal: str) -> dict[str, Any] | None:
    return next((item for item in findings if item["signal"] == signal), None)


def business_impact_for(findings: list[dict[str, Any]], count_map: dict[str, int]) -> str:
    if count_map["UNKNOWN"] >= 4:
        return "The audit could not verify enough signals to make a confident business call. Static requests may have failed, been blocked, or returned inconclusive responses."
    content = get_finding(findings, "Readable content available for AI extraction")
    if content and content["status"] == "PARTIAL":
        return "AI systems can access and parse the site, but may not have enough useful page copy to answer questions, cite pages, or recommend products confidently."
    if content and content["status"] == "MISSING":
        return "AI systems may reach the site but find little usable body content to extract, quote, or turn into answers."
    robots = get_finding(findings, "AI crawler access rules in robots.txt")
    if robots and robots["status"] in {"MISSING", "PARTIAL"}:
        return "Important AI crawlers may be prevented from seeing useful pages, which can reduce visibility in AI answers and citations."
    missing_agent_files = [
        item for item in findings
        if item["signal"] in {
            "LLM site guide available at /llms.txt",
            "Agent instruction file available at /AGENTS.md",
            "Full LLM-readable site file available at /llms-full.txt",
        } and item["status"] == "MISSING"
    ]
    if missing_agent_files:
        return "AI systems can still crawl ordinary pages, but they do not have concise guidance files that explain what the site contains and how agents should use it."
    schema = get_finding(findings, "Structured data describing products, offers, and site entities")
    if schema and schema["status"] in {"MISSING", "PARTIAL"}:
        return "AI systems can read the pages, but may miss important entities, offers, breadcrumbs, or page meaning because structured data is incomplete."
    high = [f for f in findings if f["priority"] == "HIGH" and f["status"] != "PASS"]
    if high:
        return high[0]["impact"]
    partial = [f for f in findings if f["status"] == "PARTIAL"]
    if partial:
        return partial[0]["impact"]
    return "AI-facing discovery and extraction signals are mostly present in the static sample."


def choose_main_issue(findings: list[dict[str, Any]], count_map: dict[str, int]) -> str:
    if count_map["UNKNOWN"] >= 4:
        return "The audit could not verify several signals because static requests failed or were blocked."
    content = get_finding(findings, "Readable content available for AI extraction")
    strong_technical = sum(
        1 for item in findings
        if item["area"] in {"Agent Readiness", "AI Bot Access", "Schema / Structured Data", "Technical Hygiene"} and item["status"] == "PASS"
    ) >= 6
    if content and content["status"] == "PARTIAL" and strong_technical:
        return "Pages are technically AI-ready, but the sampled pages have very thin readable content."
    if content and content["status"] == "PARTIAL":
        return "The sampled pages have readable content, but it is thin or under-structured for confident AI answers."
    if content and content["status"] == "MISSING":
        return "The sampled pages expose almost no extractable body content."
    robots = get_finding(findings, "AI crawler access rules in robots.txt")
    if robots and robots["status"] == "MISSING":
        return "Some AI crawlers may be blocked from accessing the site."
    if robots and robots["status"] == "PARTIAL":
        return "AI crawler access is present, but not clearly documented for common AI bots."
    missing_agent_files = [
        item for item in findings
        if item["signal"] in {
            "LLM site guide available at /llms.txt",
            "Agent instruction file available at /AGENTS.md",
        } and item["status"] == "MISSING"
    ]
    if missing_agent_files:
        return "The site is crawlable, but missing AI-facing guidance files."
    schema = get_finding(findings, "Structured data describing products, offers, and site entities")
    if schema and schema["status"] in {"MISSING", "PARTIAL"}:
        return "AI systems can read the pages, but structured data is incomplete."
    candidates = [f for f in sorted(findings, key=priority_sort) if f["status"] in {"MISSING", "PARTIAL", "UNKNOWN"} and f["priority"] != "NONE"]
    if not candidates:
        return "No major issue found in the limited static sample."
    return candidates[0]["impact"]


def counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    out = {"PASS": 0, "PARTIAL": 0, "MISSING": 0, "UNKNOWN": 0}
    for item in findings:
        out[item["status"]] += 1
    return out


def markdown_escape_cell(value: str) -> str:
    return clean_space(value).replace("|", "\\|").replace("\n", "<br>")


def html_escape(value: Any) -> str:
    return html.escape(clean_space(str(value)), quote=True)


def html_class(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "none"


def score_note(payload: dict[str, Any]) -> str:
    pillars = payload["pillars"]
    summary = payload["summary"]
    if summary["unknown"] >= 4:
        return "Several checks are UNKNOWN because static requests failed or were blocked, so the score is conservative."
    content_score = pillars["contentExtractionQuality"]["score"]
    strong_non_content = (
        pillars["aiBotAccess"]["score"] >= 16
        and pillars["schemaStructuredData"]["score"] >= 12
        and pillars["agentReadiness"]["score"] >= 15
        and pillars["technicalHygiene"]["score"] >= 4
    )
    if content_score < 18 and strong_non_content:
        return "The site has strong technical AI-readiness signals, but the sampled pages contain very little readable page copy. This lowers the Content & Extraction score even though agent files, schema, and metadata are present."
    if content_score < 18:
        return "The Content & Extraction score is low because sampled pages were thin, sparse, noisy, or hard to evaluate from static HTML."
    return ""


def fix_reason(action: str) -> str:
    if "page copy" in action:
        return "Gives AI systems more information to extract, cite, and use in answers."
    if "JSON-LD" in action:
        return "Helps AI systems identify entities, products, offers, breadcrumbs, and page meaning."
    if "/llms.txt" in action:
        return "Gives LLMs a concise guide to the site's most important content."
    if "AGENTS.md" in action:
        return "Gives future agents explicit guidance for how to understand and interact with the site."
    if "robots.txt" in action:
        return "Clarifies whether important AI crawlers can access useful pages."
    if "sitemap" in action or "canonical" in action or "meta description" in action:
        return "Improves basic discovery and citation context for crawlers and AI systems."
    if "/llms-full.txt" in action:
        return "Provides a fuller markdown source for deeper extraction when the site has substantial content."
    if "Accept: text/markdown" in action:
        return "Can give AI clients a cleaner extraction path than raw HTML."
    if "MCP" in action:
        return "Creates a discoverable path for agent tools when the site exposes them."
    if "landmarks" in action or "heading" in action:
        return "Helps agents separate navigation, content, page sections, and actions."
    return "Improves AI crawlability, extraction, citation, or agent readiness."


def make_fix_items(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = [
        item["recommendedAction"]
        for item in sorted(findings, key=priority_sort)
        if item["status"] != "PASS" and item["priority"] != "NONE"
    ]
    return [
        {"priority": index, "fix": action, "whyItMatters": fix_reason(action)}
        for index, action in enumerate(dedupe(actions), start=1)
    ]


def render_html_report(root: str, payload: dict[str, Any], requests: list[FetchResult], score_explanation: str, top_fix_heading: str) -> str:
    summary = payload["summary"]
    coverage = payload["coverage"]
    findings = payload["findings"]
    top_fixes = summary["topFixes"][:3]

    pillar_labels = [
        ("contentExtractionQuality", "Content & Extraction Quality"),
        ("aiBotAccess", "AI Bot Access"),
        ("schemaStructuredData", "Schema / Structured Data"),
        ("agentReadiness", "Agent Readiness"),
        ("technicalHygiene", "Technical Hygiene"),
    ]
    pillar_cards = []
    for key, label in pillar_labels:
        pillar = payload["pillars"][key]
        score = int(pillar["score"])
        max_score = int(pillar["maxScore"])
        pct = 0 if max_score == 0 else round(score / max_score * 100)
        pillar_cards.append(f"""
          <article class="score-card">
            <div class="score-card-top">
              <h3>{html_escape(label)}</h3>
              <strong>{score}<span>/{max_score}</span></strong>
            </div>
            <div class="bar"><span style="width:{pct}%"></span></div>
          </article>
        """)

    if top_fixes:
        fix_rows = "\n".join(
            f"""
            <tr>
              <td><span class="rank">{int(item['priority'])}</span></td>
              <td>{html_escape(item['fix'])}</td>
              <td>{html_escape(item['whyItMatters'])}</td>
            </tr>
            """
            for item in top_fixes
        )
        fix_table = f"""
          <table class="fix-table">
            <thead><tr><th>Priority</th><th>Fix</th><th>Why it matters</th></tr></thead>
            <tbody>{fix_rows}</tbody>
          </table>
        """
    else:
        fix_table = '<p class="muted">No high-priority fixes found in the static sample.</p>'

    sampled_pages = coverage["sampledPages"]
    coverage_cards = [
        ("Homepage checked", "Yes" if coverage["homepageChecked"] else "No"),
        ("Representative pages", str(coverage["representativePagesChecked"])),
        ("Sitemap found", "Yes" if coverage["sitemapFound"] else "No"),
        ("Crawl type", coverage["crawlType"]),
        ("Static audit note", "Limited static sample; no full-site crawl or JavaScript rendering."),
        ("Sampled URLs", ", ".join(sampled_pages) if sampled_pages else "None"),
    ]
    coverage_html = "\n".join(
        f"""
        <article class="meta-card">
          <span>{html_escape(label)}</span>
          <strong>{html_escape(value)}</strong>
        </article>
        """
        for label, value in coverage_cards
    )

    matrix_rows = "\n".join(
        f"""
        <tr>
          <td>{html_escape(item['area'])}</td>
          <td>{html_escape(item['signal'])}</td>
          <td><span class="chip status-{html_class(item['status'])}">{html_escape(item['status'])}</span></td>
          <td>{html_escape(item['impact'])}</td>
          <td>{html_escape('; '.join(item['evidence'][:2]))}</td>
          <td><span class="chip priority-{html_class(item['priority'])}">{html_escape(item['priority'])}</span></td>
        </tr>
        """
        for item in findings
    )

    appendix_items = [
        ("Audit type", payload["auditType"]),
        ("JavaScript rendered", "false"),
        ("Full crawl", "false"),
        ("Requests attempted", str(len(requests))),
        ("User-Agent", USER_AGENT),
    ]
    appendix_html = "\n".join(
        f"<li><span>{html_escape(label)}</span><strong>{html_escape(value)}</strong></li>"
        for label, value in appendix_items
    )

    score_pct = max(0, min(100, int(payload["score"])))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Site Readiness Scorecard - {html_escape(root)}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #687483;
      --line: #dce2e8;
      --accent: #2457d6;
      --accent-soft: #e8eefc;
      --pass: #157f4f;
      --pass-bg: #e7f6ee;
      --partial: #9a5a00;
      --partial-bg: #fff3d7;
      --missing: #b42318;
      --missing-bg: #fde8e6;
      --unknown: #526070;
      --unknown-bg: #edf1f5;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Arial, Helvetica, sans-serif; line-height: 1.45; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef3ff 100%); border: 1px solid var(--line); border-radius: 8px; padding: 28px; display: grid; gap: 22px; grid-template-columns: minmax(0, 1fr) 220px; box-shadow: 0 12px 30px rgba(24, 39, 75, .08); }}
    .eyebrow {{ margin: 0 0 8px; color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: 0; text-transform: uppercase; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 8px; font-size: 30px; line-height: 1.15; }}
    h2 {{ font-size: 20px; margin-bottom: 14px; }}
    h3 {{ font-size: 15px; }}
    .site {{ color: var(--accent); overflow-wrap: anywhere; font-weight: 700; }}
    .hero p {{ max-width: 760px; }}
    .score-ring {{ align-self: center; justify-self: end; width: 178px; height: 178px; border-radius: 50%; background: conic-gradient(var(--accent) {score_pct}%, #dbe3ee 0); display: grid; place-items: center; }}
    .score-inner {{ width: 132px; height: 132px; background: white; border-radius: 50%; display: grid; place-items: center; text-align: center; border: 1px solid var(--line); }}
    .score-inner strong {{ font-size: 34px; }}
    .score-inner span {{ color: var(--muted); font-size: 13px; display: block; }}
    .badge {{ display: inline-flex; padding: 6px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-weight: 700; font-size: 13px; }}
    section {{ margin-top: 24px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 20px; }}
    .score-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }}
    .score-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; min-width: 0; }}
    .score-card-top {{ min-height: 72px; display: flex; flex-direction: column; justify-content: space-between; gap: 10px; }}
    .score-card h3 {{ margin: 0; color: var(--muted); font-weight: 700; }}
    .score-card strong {{ font-size: 24px; }}
    .score-card strong span {{ color: var(--muted); font-size: 14px; }}
    .bar {{ height: 8px; background: #e8edf3; border-radius: 999px; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; background: var(--accent); border-radius: inherit; }}
    .note {{ margin: 14px 0 0; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ padding: 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    .fix-table th:first-child, .fix-table td:first-child {{ width: 90px; }}
    .rank {{ display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--accent); color: white; font-weight: 700; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .meta-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; min-width: 0; }}
    .meta-card span {{ display: block; color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 6px; }}
    .meta-card strong {{ overflow-wrap: anywhere; }}
    .matrix-wrap {{ overflow-x: auto; }}
    .matrix th:nth-child(1) {{ width: 150px; }}
    .matrix th:nth-child(2) {{ width: 230px; }}
    .matrix th:nth-child(3), .matrix th:nth-child(6) {{ width: 105px; }}
    .chip {{ display: inline-flex; align-items: center; justify-content: center; min-width: 72px; padding: 5px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; }}
    .status-pass {{ color: var(--pass); background: var(--pass-bg); }}
    .status-partial {{ color: var(--partial); background: var(--partial-bg); }}
    .status-missing {{ color: var(--missing); background: var(--missing-bg); }}
    .status-unknown {{ color: var(--unknown); background: var(--unknown-bg); }}
    .priority-high {{ color: var(--missing); background: var(--missing-bg); }}
    .priority-medium {{ color: var(--partial); background: var(--partial-bg); }}
    .priority-low {{ color: var(--unknown); background: var(--unknown-bg); }}
    .priority-none {{ color: var(--pass); background: var(--pass-bg); }}
    .appendix {{ margin: 0; padding: 0; list-style: none; }}
    .appendix li {{ display: flex; justify-content: space-between; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--line); }}
    .appendix span {{ color: var(--muted); }}
    .appendix strong {{ text-align: right; overflow-wrap: anywhere; }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 900px) {{
      .hero {{ grid-template-columns: 1fr; }}
      .score-ring {{ justify-self: start; }}
      .score-grid, .meta-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 20px, 1180px); padding-top: 10px; }}
      .hero, .panel {{ padding: 16px; }}
      h1 {{ font-size: 24px; }}
      .score-grid, .meta-grid {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 10px; }}
      .appendix li {{ display: block; }}
      .appendix strong {{ display: block; text-align: left; margin-top: 4px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="hero">
      <div>
        <p class="eyebrow">AI Site Readiness Scorecard</p>
        <h1>{html_escape(root)}</h1>
        <p class="site">Audit date: {html_escape(payload['auditDate'])}</p>
        <p><span class="badge">{html_escape(payload['readinessLevel'])}</span></p>
        <h2>{html_escape(summary['mainIssue'])}</h2>
        <p>{html_escape(summary['businessImpact'])}</p>
      </div>
      <div class="score-ring" aria-label="Overall score {int(payload['score'])} out of 100">
        <div class="score-inner"><div><strong>{int(payload['score'])}</strong><span>/ 100</span></div></div>
      </div>
    </header>

    <section class="panel">
      <h2>Score Breakdown</h2>
      <div class="score-grid">{''.join(pillar_cards)}</div>
      {f'<p class="note">{html_escape(score_explanation)}</p>' if score_explanation else ''}
    </section>

    <section class="panel">
      <h2>{html_escape(top_fix_heading.replace('## ', ''))}</h2>
      {fix_table}
    </section>

    <section class="panel">
      <h2>Audit Coverage</h2>
      <div class="meta-grid">{coverage_html}</div>
    </section>

    <section class="panel">
      <h2>Audit Matrix</h2>
      <div class="matrix-wrap">
        <table class="matrix">
          <thead><tr><th>Area</th><th>Signal</th><th>Result</th><th>Impact</th><th>Evidence</th><th>Priority</th></tr></thead>
          <tbody>{matrix_rows}</tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Technical Appendix</h2>
      <ul class="appendix">{appendix_html}</ul>
    </section>
  </main>
</body>
</html>
"""


def write_outputs(root: str, output_dir: Path, payload: dict[str, Any], pages: list[PageInfo], requests: list[FetchResult], robots_notes: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    findings = payload["findings"]
    summary = payload["summary"]

    score_rows = []
    for key, label in [
        ("contentExtractionQuality", "Content & Extraction Quality"),
        ("aiBotAccess", "AI Bot Access"),
        ("schemaStructuredData", "Schema / Structured Data"),
        ("agentReadiness", "Agent Readiness"),
        ("technicalHygiene", "Technical Hygiene"),
    ]:
        pillar = payload["pillars"][key]
        score_rows.append(f"| {label} | {pillar['score']} / {pillar['maxScore']} |")

    matrix_rows = []
    for item in findings:
        matrix_rows.append(
            "| {area} | {signal} | {status} | {impact} | {evidence} | {priority} |".format(
                area=markdown_escape_cell(item["area"]),
                signal=markdown_escape_cell(item["signal"]),
                status=item["status"],
                impact=markdown_escape_cell(item["impact"]),
                evidence=markdown_escape_cell("; ".join(item["evidence"][:2])),
                priority=item["priority"],
            )
        )

    sampled = payload["coverage"]["sampledPages"]
    top_fixes = summary["topFixes"][:3]
    top_fix_heading = "## Top Fix" if len(top_fixes) == 1 else "## Top Fixes"
    if top_fixes:
        top_fix_rows = [
            f"| {item['priority']} | {markdown_escape_cell(item['fix'])} | {markdown_escape_cell(item['whyItMatters'])} |"
            for item in top_fixes
        ]
        top_fix_table = "\n".join([
            "| Priority | Fix | Why it matters |",
            "|---:|---|---|",
            *top_fix_rows,
        ])
    else:
        top_fix_table = "No high-priority fixes found in the static sample."
    score_explanation = score_note(payload)
    coverage_lines = [
        f"- Homepage checked: {'yes' if payload['coverage']['homepageChecked'] else 'no'}",
        f"- Representative pages checked: {payload['coverage']['representativePagesChecked']}",
        f"- Sampled page URLs: {', '.join(sampled) if sampled else 'none'}",
        f"- Sitemap found: {'yes' if payload['coverage']['sitemapFound'] else 'no'}",
        "- Crawl type: Limited static sample",
        "- Note: This is not a full-site crawl and JavaScript was not rendered.",
    ]
    appendix_lines = [
        f"- Audit type: {payload['auditType']}",
        "- JavaScript rendered: false",
        "- Full crawl: false",
        f"- Requests attempted: {len(requests)}",
        f"- User-Agent: {USER_AGENT}",
    ]

    report = "\n".join([
        "# AI Site Readiness Scorecard",
        "",
        "## Snapshot",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Site | {root} |",
        f"| Audit date | {payload['auditDate']} |",
        f"| Overall score | {payload['score']} / 100 |",
        f"| Readiness level | {payload['readinessLevel']} |",
        f"| Main issue | {markdown_escape_cell(summary['mainIssue'])} |",
        f"| Business impact | {markdown_escape_cell(summary['businessImpact'])} |",
        "",
        "## Score Breakdown",
        "",
        "| Pillar | Score |",
        "| --- | ---: |",
        *score_rows,
        *(["", score_explanation] if score_explanation else []),
        "",
        top_fix_heading,
        "",
        top_fix_table,
        "",
        "## Audit Coverage",
        "",
        *coverage_lines,
        "",
        "## Audit Matrix",
        "",
        "| Area | Signal | Result | Impact | Evidence | Priority |",
        "| --- | --- | --- | --- | --- | --- |",
        *matrix_rows,
        "",
        "## Technical Appendix",
        "",
        *appendix_lines,
        "",
    ])
    (output_dir / "01-ai-readiness-scorecard.md").write_text(report, encoding="utf-8")
    html_report = render_html_report(root, payload, requests, score_explanation, top_fix_heading)
    (output_dir / "01-ai-readiness-scorecard.html").write_text(html_report, encoding="utf-8")
    (output_dir / "02-findings.json").write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    checklist_items = "\n".join(f"- [ ] {item['fix']}" for item in summary["topFixes"]) or "- [ ] No high-priority fixes found in this limited static sample."
    (output_dir / "03-fix-checklist.md").write_text("# AI Site Readiness Fix Checklist\n\n" + checklist_items + "\n", encoding="utf-8")
    write_evidence_log(output_dir, requests, pages, robots_notes)
    markdown_pages = [page for page in pages if page.markdown.strip()]
    best_page = max(markdown_pages, key=lambda p: len(p.markdown), default=None)
    sample = best_page.markdown if best_page else "# Markdown Extraction Sample\n\nNo page content could be extracted.\n"
    (output_dir / "05-markdown-extraction-sample.md").write_text(sample, encoding="utf-8")


def write_evidence_log(output_dir: Path, requests: list[FetchResult], pages: list[PageInfo], robots_notes: list[str]) -> None:
    request_lines = []
    files_checked: list[str] = []
    for result in requests:
        status = result.status if result.status is not None else "ERROR"
        extra = f" ({result.error})" if result.error else ""
        request_lines.append(f"- {result.url} -> {status}; Content-Type: {result.content_type or 'unknown'}{extra}")
        path = urllib.parse.urlparse(result.url).path or "/"
        if path not in files_checked and path != "/":
            files_checked.append(path)
    jsonld = sorted({t for page in pages for t in page.jsonld_types})
    unknowns = [f"- {r.url}: {r.error or 'HTTP ' + str(r.status)}" for r in requests if r.error or r.status is None or r.status >= 500]
    content = "\n".join([
        "# AI Site Readiness Evidence Log",
        "",
        "## URLs Requested",
        "",
        "\n".join(request_lines) or "- None",
        "",
        "## Files Checked",
        "",
        "\n".join(f"- {path}" for path in files_checked) or "- None",
        "",
        "## Sampled Pages",
        "",
        "\n".join(f"- {page.url}" for page in pages) or "- None",
        "",
        "## Headers Used",
        "",
        f"- User-Agent: {USER_AGENT}",
        "- Accept: text/html,*/*;q=0.8",
        "- Accept: text/markdown",
        "",
        "## JSON-LD Types Detected",
        "",
        "\n".join(f"- {item}" for item in jsonld) or "- None detected",
        "",
        "## Robots.txt AI Bot Findings",
        "",
        "\n".join(f"- {note}" for note in robots_notes) or "- No robots.txt AI bot findings",
        "",
        "## Unknown / Error Notes",
        "",
        "\n".join(unknowns) or "- None",
        "",
    ])
    (output_dir / "04-evidence-log.md").write_text(content, encoding="utf-8")


def audit(raw_url: str, out: str | None = None) -> Path:
    root = normalize_url(raw_url)
    slug = site_slug(root)
    output_dir = Path(out) if out else Path("output") / slug
    requests: list[FetchResult] = []

    homepage_fetch = fetch(root)
    requests.append(homepage_fetch)
    homepage = parse_page(homepage_fetch)

    sitemap, sitemap_urls = load_sitemap_urls(root, requests)
    is_ecommerce = classify_site(sitemap_urls, homepage)
    rep_urls = select_representative_urls(root, homepage, sitemap_urls, is_ecommerce)
    rep_pages: list[PageInfo] = []
    for url in rep_urls:
        result = fetch(url)
        requests.append(result)
        if result.ok:
            rep_pages.append(parse_page(result))

    pages = [homepage] + rep_pages
    fetched_pages = [page for page in pages if page.fetch.ok]
    robots = file_presence(root, "/robots.txt", requests)
    robots_status, robots_ratio, robots_evidence, robots_impact = analyze_robots(robots)

    llms = file_presence(root, "/llms.txt", requests)
    llms_status, llms_evidence = presence_status(llms, "/llms.txt")

    llms_full = file_presence(root, "/llms-full.txt", requests)
    llms_full_status, llms_full_evidence = presence_status(llms_full, "/llms-full.txt")

    agent_results = [file_presence(root, path, requests) for path in AGENT_PATHS]
    agent_pass = next((result for result in agent_results if result.ok and result.nonempty), None)
    if any(result.error for result in agent_results) and not agent_pass:
        agents_status = "UNKNOWN"
        agents_evidence = [f"{r.url}: {r.error}" for r in agent_results if r.error][:3]
    elif agent_pass:
        agents_status = "PASS"
        agents_evidence = [f"{urllib.parse.urlparse(agent_pass.url).path} returned HTTP {agent_pass.status} and non-empty content"]
    else:
        agents_status = "MISSING"
        agents_evidence = ["No checked AGENTS.md path returned non-empty HTTP 200 content"]

    schema_status, schema_score, schema_evidence, schema_impact, schema_action = evaluate_schema(fetched_pages, is_ecommerce)
    semantic_status, semantic_ratio, semantic_evidence = evaluate_semantic_html(fetched_pages)
    content_status, content_score, content_evidence, content_impact, content_action = evaluate_content(fetched_pages)
    markdown_status = "PASS" if any(page.markdown.strip() for page in fetched_pages) else "UNKNOWN"
    markdown_score = 3 if markdown_status == "PASS" else 0
    accept_status, accept_score, accept_evidence = evaluate_accept_markdown(root, requests)
    mcp_status, mcp_score, mcp_evidence = evaluate_mcp(root, homepage, robots, llms if llms.ok else None, agent_pass, requests)
    hygiene_status, hygiene_score, hygiene_evidence, hygiene_impact = technical_hygiene(homepage, sitemap)

    ai_bot_score = round(20 * robots_ratio) if robots_status in {"PASS", "PARTIAL", "MISSING"} else 0
    semantic_agent_score = 2 if semantic_status == "PASS" else 1 if semantic_status == "PARTIAL" else 0
    llms_score = status_points(llms_status, 5, 2)
    agents_score = status_points(agents_status, 5, 2)
    llms_full_score = status_points(llms_full_status, 3, 1)
    agent_readiness_score = llms_score + agents_score + llms_full_score + accept_score + mcp_score + semantic_agent_score

    findings = [
        finding("Content & Extraction Quality", "Readable content available for AI extraction", content_status, content_score, 35, content_impact, content_evidence[:3], "HIGH" if content_status in {"MISSING", "UNKNOWN"} else "MEDIUM" if content_status == "PARTIAL" else "NONE", content_action),
        finding("AI Bot Access", "AI crawler access rules in robots.txt", robots_status, ai_bot_score, 20, robots_impact, robots_evidence, "HIGH" if robots_status == "MISSING" else "MEDIUM" if robots_status in {"PARTIAL", "UNKNOWN"} else "NONE", "Clarify AI crawler access in robots.txt without assuming missing directives are good or bad."),
        finding("Schema / Structured Data", "Structured data describing products, offers, and site entities", schema_status, schema_score, 20, schema_impact, schema_evidence, "HIGH" if schema_status == "MISSING" else "MEDIUM" if schema_status == "PARTIAL" else "NONE", schema_action),
        finding("Agent Readiness", "LLM site guide available at /llms.txt", llms_status, llms_score, 5, "LLMs do not have a clean site guide." if llms_status != "PASS" else "A clean LLM site guide is available.", llms_evidence, "HIGH" if llms_status != "PASS" else "NONE", "Add /llms.txt."),
        finding("Agent Readiness", "Agent instruction file available at /AGENTS.md", agents_status, agents_score, 5, "Future agents lack explicit operating guidance." if agents_status != "PASS" else "Agent guidance is discoverable.", agents_evidence, "HIGH" if agents_status != "PASS" else "NONE", "Add /AGENTS.md or a common discoverable variant."),
        finding("Agent Readiness", "Full LLM-readable site file available at /llms-full.txt", llms_full_status, llms_full_score, 3, "Deep extraction may lack a complete markdown knowledge source." if llms_full_status != "PASS" else "A fuller LLM-readable source is available.", llms_full_evidence, "HIGH" if llms_full_status != "PASS" and is_ecommerce else "MEDIUM" if llms_full_status != "PASS" else "NONE", "Add /llms-full.txt when the site has substantial product, policy, documentation, or service content."),
        finding("Agent Readiness", "Markdown response support through Accept header", accept_status, accept_score, 3, "Markdown negotiation can make extraction cleaner for AI clients." if accept_status != "PASS" else "Markdown content negotiation is available.", accept_evidence, "MEDIUM" if accept_status == "UNKNOWN" else "LOW" if accept_status != "PASS" else "NONE", "Consider serving markdown-like responses when clients request Accept: text/markdown."),
        finding("Agent Readiness", "Discoverable MCP or agent-tooling reference", mcp_status, mcp_score, 2, "Agents may not discover machine-usable tools or endpoints from static signals." if mcp_status != "PASS" else "MCP discovery signal is present.", mcp_evidence, "LOW" if mcp_status != "PASS" else "NONE", "Add a discoverable MCP reference if the site exposes agent tools."),
        finding("Agent Readiness", "Semantic page structure for AI parsing", semantic_status, semantic_agent_score, 2, "Semantic landmarks help agents segment page content and actions.", semantic_evidence[:3], "MEDIUM" if semantic_status == "MISSING" else "LOW" if semantic_status == "PARTIAL" else "NONE", "Improve landmarks, heading hierarchy, aria labels, and role usage where appropriate."),
        finding("Content & Extraction Quality", "Markdown extraction sample", markdown_status, markdown_score, 3, "A clean markdown extraction sample shows whether useful page text can be lifted from static HTML.", ["Markdown sample was generated from the best available sampled page"] if markdown_status == "PASS" else ["No markdown sample could be generated"], "NONE" if markdown_status == "PASS" else "LOW", "Improve static text availability so a markdown sample can be extracted."),
        finding("Technical Hygiene", "Basic metadata and accessibility", hygiene_status, hygiene_score, 5, hygiene_impact, hygiene_evidence, "MEDIUM" if hygiene_status == "MISSING" else "LOW" if hygiene_status == "PARTIAL" else "NONE", "Fix missing sitemap, canonical, title, meta description, or HTTP accessibility issues."),
    ]

    pillar_scores = {
        "contentExtractionQuality": {"score": min(35, content_score), "maxScore": 35},
        "aiBotAccess": {"score": min(20, ai_bot_score), "maxScore": 20},
        "schemaStructuredData": {"score": min(20, schema_score), "maxScore": 20},
        "agentReadiness": {"score": min(20, agent_readiness_score), "maxScore": 20},
        "technicalHygiene": {"score": min(5, hygiene_score), "maxScore": 5},
    }
    total = sum(item["score"] for item in pillar_scores.values())
    count_map = counts(findings)
    fixes = make_fix_items(findings)
    payload: dict[str, Any] = {
        "url": root,
        "siteSlug": slug,
        "auditType": "limited_static_sample",
        "auditDate": dt.date.today().isoformat(),
        "score": total,
        "readinessLevel": readiness_level(total),
        "summary": {
            "pass": count_map["PASS"],
            "partial": count_map["PARTIAL"],
            "missing": count_map["MISSING"],
            "unknown": count_map["UNKNOWN"],
            "mainIssue": choose_main_issue(findings, count_map),
            "businessImpact": business_impact_for(findings, count_map),
            "topFixes": fixes[:8],
        },
        "coverage": {
            "homepageChecked": homepage_fetch.ok,
            "representativePagesChecked": len(rep_pages),
            "sampledPages": [page.url for page in rep_pages],
            "sitemapFound": sitemap.ok and sitemap.nonempty,
            "crawlType": "Limited static sample",
            "fullCrawl": False,
            "javascriptRendered": False,
        },
        "pillars": pillar_scores,
        "findings": findings,
    }
    write_outputs(root, output_dir, payload, pages, requests, robots_evidence)
    return output_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a limited static AI/LLM readiness audit and create a scorecard output packet.",
    )
    parser.add_argument("url", help="Website URL to audit, for example https://example.com")
    parser.add_argument("--out", help="Output directory. Defaults to output/{site-slug}.")
    args = parser.parse_args(argv)
    try:
        output_dir = audit(args.url, args.out)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Created AI readiness audit packet: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
