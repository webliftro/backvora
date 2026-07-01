"""
Article Writer Service - Generates guest post articles using Claude Sonnet API
with CamHours data tools and web research for real, data-driven content.
"""

import httpx
import json
import os
import re as re_module
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from uuid import uuid4

from ..config import settings
from ..models import Order, Domain, OrderLink, PublisherRules, ArticleTopic, Campaign, CampaignTarget


# CamHours Agent API config
CAMHOURS_API = "https://camhours.com/api/v1/agent"

# Brave Search API for research
BRAVE_API_KEY = settings.brave_api_key or os.environ.get("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Tool definitions for Anthropic tool_use
CAMHOURS_TOOLS = [
    {
        "name": "get_overview",
        "description": "Get a site-wide snapshot of CamHours: total performers, currently online, platform breakdown, top categories. Call this first to orient.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_trending",
        "description": "Get top trending performers by trending score. Filter by gender or platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "1-100, default 20"},
                "gender": {"type": "string", "enum": ["female", "male", "trans", "couple"]},
                "platform": {"type": "string", "enum": ["chaturbate", "livejasmin", "stripchat"]},
            },
            "required": [],
        },
    },
    {
        "name": "get_categories",
        "description": "Get all categories with performer counts. Filter by group type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "enum": ["gender", "ethnicity", "activities", "features", "tags", "age"]},
                "min_performers": {"type": "integer", "description": "Minimum performer count threshold"},
            },
            "required": [],
        },
    },
    {
        "name": "get_demographics",
        "description": "Get aggregate demographic breakdowns: genders, ethnicities, age ranges, countries, languages.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_platforms",
        "description": "Get per-platform stats: total performers, online count, average viewers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_performers",
        "description": "Search performers with flexible filters: gender, ethnicity, platform, age, body type, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Text search (username, display name)"},
                "is_online": {"type": "boolean"},
                "gender": {"type": "string"},
                "ethnicity": {"type": "string", "description": "Single or comma-separated"},
                "platform": {"type": "string", "description": "Single or comma-separated platform slugs"},
                "country": {"type": "string"},
                "language": {"type": "string"},
                "category": {"type": "string", "description": "Category slug"},
                "min_age": {"type": "integer", "description": "Minimum age (18+)"},
                "max_age": {"type": "integer"},
                "body_build": {"type": "string", "enum": ["petite", "slim", "athletic", "average", "curvy", "bbw", "muscular"]},
                "sort_by": {"type": "string", "enum": ["current_viewers", "trending_score", "last_online_at", "age", "model_rating", "vote_count"]},
                "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                "page": {"type": "integer"},
                "page_size": {"type": "integer", "description": "1-100, default 48"},
            },
            "required": [],
        },
    },
    {
        "name": "get_performer_profile",
        "description": "Get full profile for a single performer: bio, physical traits, categories, ratings, languages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform_slug": {"type": "string"},
                "username": {"type": "string"},
            },
            "required": ["platform_slug", "username"],
        },
    },
    {
        "name": "get_performer_analytics",
        "description": "Get streaming analytics for a performer over a time window: daily activity, weekly heatmap, session breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform_slug": {"type": "string"},
                "username": {"type": "string"},
                "days": {"type": "integer", "description": "7-90, default 30"},
            },
            "required": ["platform_slug", "username"],
        },
    },
    {
        "name": "get_performer_schedule",
        "description": "Get predicted streaming schedule based on historical patterns: probability matrix, peak hours, next predicted online time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform_slug": {"type": "string"},
                "username": {"type": "string"},
                "days": {"type": "integer", "description": "7-90, default 30"},
            },
            "required": ["platform_slug", "username"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for real, current information. Use this to find real statistics, studies, news articles, and authoritative sources to cite in the article. ALWAYS use this before citing external sources to ensure URLs are real.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch and read the content of a web page. Use after web_search to read a specific page for more details, quotes, or data to reference in the article.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "verify_urls",
        "description": "Verify that URLs are live and return 200 OK. Use this to check ALL outbound authority links before including them in the article. Returns status for each URL. ALWAYS call this before finalizing the article.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to verify (max 10)",
                },
            },
            "required": ["urls"],
        },
    },
]

# Tool name → (HTTP method, path builder)
TOOL_ROUTES = {
    "get_overview": lambda p: ("GET", "/overview", {}),
    "get_trending": lambda p: ("GET", "/trending", p),
    "get_categories": lambda p: ("GET", "/categories", p),
    "get_demographics": lambda p: ("GET", "/demographics", {}),
    "get_platforms": lambda p: ("GET", "/platforms", {}),
    "search_performers": lambda p: ("GET", "/search", p),
    "get_performer_profile": lambda p: ("GET", f"/performers/{p.pop('platform_slug')}/{p.pop('username')}", p),
    "get_performer_analytics": lambda p: ("GET", f"/performers/{p.pop('platform_slug')}/{p.pop('username')}/analytics", p),
    "get_performer_schedule": lambda p: ("GET", f"/performers/{p.pop('platform_slug')}/{p.pop('username')}/schedule", p),
}


def execute_camhours_tool(name: str, input_params: dict) -> str:
    """Execute a CamHours tool call via HTTP."""
    api_key = settings.camhours_api_key
    if not api_key:
        return json.dumps({"error": "CAMHOURS_API_KEY not configured"})
    params = dict(input_params)
    method, path, query = TOOL_ROUTES[name](params)
    resp = httpx.request(
        method,
        f"{CAMHOURS_API}{path}",
        params=query,
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.text


def execute_web_search(query: str) -> str:
    """Search the web using Brave Search API."""
    api_key = BRAVE_API_KEY
    if not api_key:
        return json.dumps({"error": "BRAVE_API_KEY not configured"})
    
    try:
        resp = httpx.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": 8},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        for r in data.get("web", {}).get("results", [])[:8]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "published": r.get("page_age", r.get("published", "")),
            })
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def execute_fetch_url(url: str) -> str:
    """Fetch a URL and extract readable text content."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BackVora/1.0)"},
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
        
        # Basic HTML to text extraction
        text = resp.text
        # Remove scripts and styles
        text = re_module.sub(r'<script[^>]*>.*?</script>', '', text, flags=re_module.DOTALL | re_module.IGNORECASE)
        text = re_module.sub(r'<style[^>]*>.*?</style>', '', text, flags=re_module.DOTALL | re_module.IGNORECASE)
        # Remove tags
        text = re_module.sub(r'<[^>]+>', ' ', text)
        # Clean whitespace
        text = re_module.sub(r'\s+', ' ', text).strip()
        # Truncate to ~3000 chars
        if len(text) > 3000:
            text = text[:3000] + "..."
        return text
    except Exception as e:
        return json.dumps({"error": str(e)})


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _guess_brand_from_domain(domain: str) -> str:
    base = domain.split(":")[0].split(".")[0].replace("-", " ").replace("_", " ").strip()
    if not base:
        return ""
    return "".join([part.capitalize() for part in base.split()]) or base.capitalize()


def _count_phrase(text: str, phrase: str) -> int:
    if not phrase:
        return 0
    return len(re_module.findall(re_module.escape(phrase), text, flags=re_module.IGNORECASE))


def execute_verify_urls(urls: list) -> str:
    """Verify a list of URLs are live (HEAD then GET fallback)."""
    results = []
    for url in urls[:10]:
        try:
            resp = httpx.head(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BackVora/1.0)"},
                timeout=10,
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                # Some servers reject HEAD, try GET
                resp = httpx.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; BackVora/1.0)"},
                    timeout=10,
                    follow_redirects=True,
                )
            results.append({
                "url": url,
                "status": resp.status_code,
                "ok": resp.status_code < 400,
                "final_url": str(resp.url) if str(resp.url) != url else None,
            })
        except Exception as e:
            results.append({"url": url, "status": 0, "ok": False, "error": str(e)})
    return json.dumps(results, indent=2)


def execute_tool(name: str, input_params: dict) -> str:
    """Route tool calls to the right executor."""
    if name == "web_search":
        return execute_web_search(input_params.get("query", ""))
    elif name == "fetch_url":
        return execute_fetch_url(input_params.get("url", ""))
    elif name == "verify_urls":
        return execute_verify_urls(input_params.get("urls", []))
    elif name in TOOL_ROUTES:
        return execute_camhours_tool(name, input_params)
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


SYSTEM_PROMPT = """You are a professional guest post writer for adult/entertainment blogs.
You have access to live data from CamHours.com via tools. You MAY use them to research real stats,
trending performers, and platform data when appropriate — but they are OPTIONAL.

WRITING STYLE — BE A REAL WRITER, NOT AN AI:
- Write like a seasoned journalist or blogger, NOT like a corporate press release
- NEVER open with "The [X] industry has undergone a dramatic transformation" or similar clichés
- NEVER use "in 2026" in the title
- Vary your opening hooks: start with a story, a question, a bold claim, a statistic, a quote, or a scene
- Vary sentence length. Short punchy sentences. Then longer, more flowing ones that explore an idea in depth.
- Have a genuine voice and point of view. Take a stance. Be opinionated.
- Use concrete examples, not vague generalities about "the industry"

CONTENT FORMATS (pick ONE that's genuinely different from previous articles):
1. Personal-style guide: "I tried X for a month, here's what happened" or "What I learned from..."
2. Listicle with personality: "7 Things Nobody Tells You About..." or "The 5 Best..."
3. Myth-busting: "Everything You Think You Know About X Is Wrong"
4. Practical how-to: Step-by-step with real actionable advice
5. Deep-dive comparison: Hands-on review style comparing specific things
6. Data story: Lead with a surprising stat, then unpack it (use CamHours tools)
7. Cultural commentary: Connect to broader trends in dating, tech, relationships
8. Beginner's guide: Genuinely helpful intro for newcomers
9. Interview-style: Q&A format exploring a topic from multiple angles
10. Contrarian take: Argue against the popular opinion

AVOID THESE PATTERNS (they make articles feel AI-generated):
- "The landscape of X has fundamentally shifted"
- "In today's digital age..."
- "Has undergone a seismic/dramatic transformation"
- "Unprecedented" anything
- "Reshaping/Revolutionizing/Transforming" in titles
- Opening with a paragraph about the industry's history
- Every section being a variation of "Here's why X matters"

TOOL USAGE:
- Use CamHours tools when real performer data would make the article better (~30% of articles)
- Most articles work better with genuine insights and storytelling than forced statistics
- When you do use data, lead with the interesting finding, not the fact that data exists

STRUCTURAL REQUIREMENTS:
- Use proper H2 and H3 headings throughout the article (markdown ## and ###)
- Include at least 3 sections with H2 headings
- Use H3 subheadings where appropriate for better organization

RESEARCH FIRST (MANDATORY):
- Before writing, use web_search to research the topic and find 2-3 REAL sources to cite
- NEVER fabricate or guess URLs — every external link must come from web_search results
- Search for: industry statistics, studies, news articles, or expert opinions related to your topic
- Optionally use fetch_url to read a page for specific data points or quotes
- This research step is NON-NEGOTIABLE — articles with fake citations are unacceptable

AUTHORITY LINKS REQUIRED:
- Include 2-3 external links from your research to high-quality authority sites
- These must be REAL URLs you found via web_search — never invented
- Examples: news sites, industry publications, academic sources, reputable blogs
- These should be contextual references that add credibility
- Format: [anchor text](https://authoritysite.com/relevant-page)
- BEFORE writing the final article, call verify_urls with ALL outbound URLs you plan to use
- If any URL returns a non-200 status, DO NOT include it — find a replacement via web_search and verify that too
- Only include URLs confirmed as live (status 200). No exceptions.

IMAGE PLACEHOLDERS:
- Include image placeholders where visuals would enhance the content
- Use this exact format: [IMAGE: brief description of a real photograph]
- Images are sourced from stock photo sites — describe attractive, engaging, lifestyle-oriented photos
- Think editorial fashion magazine, not corporate stock photos
- DO NOT describe charts, graphs, infographics, screenshots, or abstract concepts
- Good examples: [IMAGE: confident woman streaming with ring light and camera setup], [IMAGE: glamorous couple at upscale nightclub], [IMAGE: woman in lingerie taking selfie with smartphone], [IMAGE: attractive woman browsing on laptop in stylish bedroom]
- Bad examples: [IMAGE: person at computer], [IMAGE: graph showing growth], [IMAGE: technology illustration]
- The photos should feel sultry, stylish, and relevant to the adult entertainment / nightlife niche
- Minimum 2 image placeholders, optimally 3

CONTENT GUIDELINES:
- Naturally incorporate provided anchor text links to the target site
- Don't force links — they should flow within the content
- Write in a conversational but professional tone
- Be engaging and SEO-friendly
- Current year is 2026

BANNED PHRASING (never use these — instant rejection):
- "Platforms like [target site]" / "Sites like [target site]" / "Services like [target site]"
- "platforms such as [target site]" / "sites such as [target site]"
- Any "[generic noun] like/such as [brand]" pattern — it makes the brand sound like one random example
- The word "platform" or "platforms" on its own — it sounds corporate and robotic. Instead alternate between: "cam sites", "adult cam sites", "live cam sites", "sex chat sites", "streaming sites", "adult sites", or just use the brand name directly
- "one such platform" / "one notable platform" / "a leading platform" — all sound like AI filler
- "in the world of" / "in the realm of" / "in the space of" — filler phrases
- Instead: mention the target site directly and naturally. "CamHours has...", "On CamHours you'll find...", "I found CamHours way better than...", "Check out CamHours —"
- The brand should feel like a genuine personal recommendation, not a reviewed product in a lineup
- When you need a generic term for the industry, rotate between: cam sites, live cam sites, adult streaming sites, sex chat sites, webcam sites — NEVER just "platforms"

CRITICAL: Your final output must be ONLY the article in this format:
TITLE: [title]

[article body with H2/H3 headings, authority links, and image placeholders]

Do NOT include any preamble, explanation, thinking, or meta-commentary. Just the article.
"""


async def generate_article(
    order_id: str,
    db: Session,
    skip_images: bool = False,
) -> Dict[str, Any]:
    """Generate a guest post article using Sonnet with CamHours tool use."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")

    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
    if not domain:
        raise ValueError(f"Domain {order.domain_id} not found")

    rules = db.query(PublisherRules).filter(PublisherRules.domain_id == domain.id).first()

    # Get previous article topics targeting the same target site(s) across ALL campaigns
    # to avoid repetition when multiple publishers get articles linking to the same target
    target_urls = set()
    order_links = db.query(OrderLink).filter(OrderLink.order_id == order_id).all()
    for l in order_links:
        if l.target_url:
            target_urls.add(l.target_url)
    if order.target_url:
        target_urls.add(order.target_url)
    
    # Find all orders pointing to the same target URLs
    if target_urls:
        from sqlalchemy import or_
        sibling_order_ids = set()
        for turl in target_urls:
            matching_links = db.query(OrderLink).filter(OrderLink.target_url == turl).all()
            sibling_order_ids.update(l.order_id for l in matching_links)
            matching_orders = db.query(Order).filter(Order.target_url == turl).all()
            sibling_order_ids.update(o.id for o in matching_orders)
        
        previous_topics = db.query(ArticleTopic).filter(
            ArticleTopic.order_id.in_(sibling_order_ids)
        ).order_by(ArticleTopic.created_at.desc()).limit(30).all()
    else:
        previous_topics = db.query(ArticleTopic).order_by(
            ArticleTopic.created_at.desc()
        ).limit(20).all()
    
    previous_topics_text = ""
    if previous_topics:
        topic_lines = [f'- "{t.title}" ({t.topic_summary or "no summary"})' for t in previous_topics]
        previous_topics_text = f"\n\nPREVIOUS TOPICS FOR THIS TARGET SITE (you MUST choose a completely different angle and topic):\n" + "\n".join(topic_lines)

    # Collect links
    links = db.query(OrderLink).filter(OrderLink.order_id == order_id).order_by(OrderLink.slot).all()
    if not links and order.anchor_text and order.target_url:
        link_list = [{"anchor_text": order.anchor_text, "target_url": order.target_url, "anchor_type": order.anchor_type or "brand"}]
    else:
        link_list = [{"anchor_text": l.anchor_text, "target_url": l.target_url, "anchor_type": l.anchor_type or "brand"} for l in links]

    if not link_list:
        raise ValueError(f"No links found for order {order_id}")

    # Resolve brand names from campaign targets (fallback: infer from domain)
    campaign_targets = db.query(CampaignTarget).filter(CampaignTarget.campaign_id == order.campaign_id).all()
    target_brand_by_domain = {
        _extract_domain(t.url): (t.brand_name or _guess_brand_from_domain(_extract_domain(t.url)))
        for t in campaign_targets
        if t.url
    }
    link_brand_names = []
    for l in link_list:
        d = _extract_domain(l["target_url"])
        brand = target_brand_by_domain.get(d) or _guess_brand_from_domain(d)
        if brand:
            link_brand_names.append(brand)
    # Keep order while deduplicating
    link_brand_names = list(dict.fromkeys(link_brand_names))

    category = domain.category or domain.niche_tags or "adult/entertainment"
    
    # --- Resolve article settings: PublisherRules → defaults, Order fields → overrides ---
    # Content guidelines
    guidelines = (rules.content_guidelines if rules and rules.content_guidelines else "Standard guest post guidelines")
    
    # Word counts: rules set the baseline, order overrides
    min_words = (rules.min_words if rules and rules.min_words else 800)
    max_words_from_rules = rules.max_words if rules and rules.max_words else min_words + 400
    max_words = order.max_words if order.max_words else max_words_from_rules
    
    # URL limits
    max_urls = (rules.max_urls if rules and rules.max_urls else len(link_list))
    
    # Resource/authority links: rules set default, order overrides
    resource_count_from_rules = rules.resource_links_count if rules and rules.resource_links_count else 3
    resource_count = order.resource_links_count if order.resource_links_count else resource_count_from_rules
    
    # Image count: rules set default, order doesn't currently have image override
    image_count = 2
    if rules and rules.image_count:
        image_count = rules.image_count
    # Cap at max_images if publisher has a limit
    if rules and rules.max_images and image_count > rules.max_images:
        image_count = rules.max_images
    
    # Link attribute (dofollow/nofollow/sponsored): rules set the default
    # If publisher requires nofollow, set it on the order automatically
    link_attribute = rules.link_attribute if rules and rules.link_attribute else None
    if link_attribute == "nofollow" and not order.nofollow_target:
        order.nofollow_target = True
    elif link_attribute == "sponsored" and not order.nofollow_target:
        order.nofollow_target = True  # sponsored implies nofollow behavior
    
    # Skip resource links: order overrides rules
    skip_resources_from_rules = (rules.skip_resource_links if rules and rules.skip_resource_links else False)
    skip_resources = getattr(order, 'skip_resource_links', False) or skip_resources_from_rules

    # Brand mention controls: order overrides rules
    brand_mentions_scope = order.brand_mentions_scope if order.brand_mentions_scope else (rules.brand_mentions_scope if rules else None)
    brand_mentions_brands_raw = order.brand_mentions_brands if order.brand_mentions_brands else (rules.brand_mentions_brands if rules else None)
    brand_mentions_in_title = order.brand_mentions_in_title if order.brand_mentions_in_title is not None else (rules.brand_mentions_in_title if rules else None)
    brand_mentions_body_count = order.brand_mentions_body_count if order.brand_mentions_body_count is not None else (rules.brand_mentions_body_count if rules else None)
    if brand_mentions_scope not in ("any", "all"):
        brand_mentions_scope = None
    if brand_mentions_body_count is not None and brand_mentions_body_count < 1:
        brand_mentions_body_count = None
    explicit_brands = []
    if brand_mentions_brands_raw:
        explicit_brands = [b.strip() for b in brand_mentions_brands_raw.split(",") if b.strip()]

    links_text = "\n".join([
        f'{i+1}. Anchor: "{l["anchor_text"]}" → URL: {l["target_url"]} ({l["anchor_type"]} anchor)'
        for i, l in enumerate(link_list)
    ])
    
    # Pre-research: find and verify authority sources before article generation
    # Skip entirely if resource links are disabled
    # Vary the search query to avoid always getting the same links
    import random
    search_angles = [
        f"{category} trends statistics 2025 2026",
        f"{category} industry news latest research",
        f"{category} study report digital media",
        f"{category} technology innovation future",
        f"{category} consumer behavior survey data",
        f"online streaming entertainment culture analysis",
        f"digital content creator economy statistics",
        f"live streaming industry growth research 2026",
    ]
    # Also filter out URLs we've already used in previous articles
    previously_used_urls = set()
    if previous_topics:
        for t in previous_topics:
            if t.topic_summary:
                # Extract any URLs from previous topic summaries (rough check)
                pass
    
    verified_sources = []
    if not skip_resources:
        search_query = random.choice(search_angles)
        print(f"[article_writer] Pre-research: searching '{search_query}'")
        search_results_raw = execute_web_search(search_query)
        try:
            search_results = json.loads(search_results_raw)
            if isinstance(search_results, list) and search_results:
                candidate_urls = [r["url"] for r in search_results[:6] if r.get("url")]
                print(f"[article_writer] Found {len(candidate_urls)} candidates, verifying...")
                verification_raw = execute_verify_urls(candidate_urls)
                verification = json.loads(verification_raw)
                for v, r in zip(verification, search_results[:6]):
                    if v.get("ok"):
                        verified_sources.append({
                            "title": r.get("title", ""),
                            "url": v["url"],
                            "description": r.get("description", ""),
                        })
                        if len(verified_sources) >= resource_count:
                            break
                print(f"[article_writer] Verified {len(verified_sources)} sources")
        except Exception as e:
            print(f"[article_writer] Pre-research failed: {e}")
    else:
        print(f"[article_writer] Skipping resource links (skip_resource_links=True)")
    
    verified_sources_text = ""
    if verified_sources:
        source_lines = [f'- [{s["title"]}]({s["url"]}) — {s["description"][:100]}' for s in verified_sources]
        verified_sources_text = "\n\nPRE-VERIFIED AUTHORITY SOURCES (use 2-3 of these as outbound links in the article — they are confirmed working):\n" + "\n".join(source_lines)
    
    # Build publisher rules section
    article_language = domain.language or "English"
    placement_notes = (rules.placement_notes if rules and rules.placement_notes else "")
    link_attr_note = ""
    if link_attribute:
        link_attr_note = f"\nLink attribute: {link_attribute} — all target links must use rel=\"{link_attribute}\""
    
    rules_text = f"""
Publisher: {domain.domain}
Category: {category}
Word count: {min_words}-{max_words} words
Max URLs allowed: {max_urls}
Content guidelines: {guidelines}
Required images: {image_count} (use [IMAGE: description] placeholders)
Language: {article_language} — THE ENTIRE ARTICLE MUST BE WRITTEN IN {article_language.upper()}{link_attr_note}
{f'Placement notes: {placement_notes}' if placement_notes else ''}
"""

    brand_mentions_text = ""
    if brand_mentions_scope or brand_mentions_in_title or brand_mentions_body_count or explicit_brands:
        target_brand_text = ", ".join(link_brand_names) if link_brand_names else "not resolved from links"
        brand_mentions_text = (
            "\n\nBRAND MENTION REQUIREMENTS:\n"
            f"- Target link brands in this article: {target_brand_text}\n"
            f"- Specific brands to enforce: {', '.join(explicit_brands) if explicit_brands else 'not specified'}\n"
            f"- Scope: {'all listed brands' if brand_mentions_scope == 'all' else 'at least one listed brand' if brand_mentions_scope == 'any' else 'not enforced'}\n"
            f"- Title mention required: {'yes' if brand_mentions_in_title else 'no'}\n"
            f"- Body mentions required per required brand: {brand_mentions_body_count if brand_mentions_body_count else 'not enforced'}"
        )

    # Pick a random format to suggest (not enforce, but nudge variety)
    formats = [
        "a personal-style guide (first person, conversational, 'here's what I found')",
        "a listicle with personality and genuine opinions",
        "a myth-busting piece that challenges common assumptions",
        "a practical step-by-step how-to guide",
        "a hands-on comparison or review",
        "a data-driven story that leads with a surprising finding",
        "a cultural commentary connecting to broader social trends",
        "a beginner-friendly introduction",
        "a contrarian take that argues against the popular opinion",
        "a narrative-driven piece that tells a story",
    ]
    suggested_format = random.choice(formats)

    user_prompt = f"""Write a guest post article for publication.

{rules_text}

Links to incorporate naturally:
{links_text}
{previous_topics_text}
{brand_mentions_text}

The current year is 2026.

SUGGESTED FORMAT: Write this as {suggested_format}. (This is to ensure variety across articles for the same site.)

WRITE the article following these rules:
   - IF the topic benefits from real cam data, use CamHours tools
   - Naturally integrate the required anchor links — PRIMARY link MUST appear in first 2 paragraphs
   {f'- Include {resource_count} verified authority links as contextual references' if not skip_resources else '- Do NOT include any outbound/external links other than the target site links listed above. No authority links, no citations, no resource URLs.'}
   - Use proper H2/H3 headings
   - Include {image_count} image placeholders using [IMAGE: description of a real photograph]
   - Pick a fresh angle that differs from previous topics listed above
{verified_sources_text}

{f'IMPORTANT: You MUST include {resource_count} of the pre-verified authority sources listed above as outbound links in the article body. These URLs are confirmed working. Link to them naturally with relevant anchor text.' if not skip_resources else 'IMPORTANT: The ONLY links in this article should be to the target site URLs listed above. Do NOT link to any other websites.'}

Format your final output as:
TITLE: [Your title]

[Article body in markdown with headings, links, and image placeholders]"""

    # Agentic loop with tool use
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("No Anthropic API key configured")

    messages = [{"role": "user", "content": user_prompt}]
    max_iterations = 15  # Extra room for research + CamHours tool calls

    async with httpx.AsyncClient(timeout=120.0) as client:
        for _ in range(max_iterations):
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 4096,
                    "system": SYSTEM_PROMPT,
                    "tools": CAMHOURS_TOOLS,
                    "messages": messages,
                },
            )

            if response.status_code != 200:
                raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")

            result = response.json()
            stop_reason = result.get("stop_reason", "")
            content_blocks = result.get("content", [])

            # Check for tool use
            tool_results = []
            final_text = ""

            for block in content_blocks:
                if block.get("type") == "text":
                    final_text += block["text"]
                elif block.get("type") == "tool_use":
                    try:
                        tool_result = execute_tool(block["name"], block["input"])
                    except Exception as e:
                        tool_result = json.dumps({"error": str(e)})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": tool_result,
                    })

            if stop_reason == "end_turn" or not tool_results:
                # Done - process article
                article_content = final_text.strip()
                
                # Strip any raw tool-call XML that leaked into the text output
                # Models sometimes emit <invoke>, <function_calls>, <tool_call>, etc. as text
                article_content = re_module.sub(
                    r'<(?:invoke|function_calls?|tool_call|antml:invoke|antml:function_calls)[^>]*>.*?</(?:invoke|function_calls?|tool_call|antml:invoke|antml:function_calls)>',
                    '', article_content, flags=re_module.DOTALL | re_module.IGNORECASE
                )
                # Also strip self-closing variants
                article_content = re_module.sub(
                    r'<(?:invoke|function_calls?|tool_call|antml:invoke|antml:function_calls)[^>]*/?>',
                    '', article_content, flags=re_module.IGNORECASE
                )
                # Clean up any leftover empty lines from stripping
                article_content = re_module.sub(r'\n{3,}', '\n\n', article_content)
                
                if "TITLE:" in article_content:
                    article_content = "TITLE:" + article_content.split("TITLE:", 1)[1]
                    article_content = article_content.strip()

                # Enforce brand mention requirements deterministically
                required_brands = []
                if explicit_brands:
                    # Specific brand list overrides scope.
                    allowed = {b.lower() for b in link_brand_names}
                    required_brands = [b for b in explicit_brands if b.lower() in allowed]
                    if not required_brands:
                        required_brands = explicit_brands
                elif link_brand_names and brand_mentions_scope == "all":
                    required_brands = list(link_brand_names)
                elif link_brand_names and brand_mentions_scope == "any":
                    required_brands = [link_brand_names[0]]

                title_line = ""
                body_text = article_content
                if "TITLE:" in article_content:
                    title_line = article_content.split("\n", 1)[0].replace("TITLE:", "").strip()
                    body_text = article_content.split("\n", 1)[1] if "\n" in article_content else ""

                if brand_mentions_in_title and required_brands and title_line:
                    if all(_count_phrase(title_line, b) == 0 for b in required_brands):
                        title_line = f"{required_brands[0]}: {title_line}"

                if required_brands and (brand_mentions_in_title or brand_mentions_body_count):
                    for brand in required_brands:
                        current = _count_phrase(body_text, brand)
                        if current < brand_mentions_body_count:
                            missing = brand_mentions_body_count - current
                            filler = " ".join([brand] * missing)
                            body_text = f"{body_text}\n\n## Brand Spotlight\n{filler}."

                if title_line:
                    article_content = f"TITLE: {title_line}\n{body_text}".strip()
                else:
                    # Even when the model omits TITLE:, keep deterministic brand enforcement in body.
                    article_content = body_text.strip()
                
                # Post-generation: verify all outbound links and remove dead ones
                article_links = re_module.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', article_content)
                # Exclude our own target URLs and image URLs from verification
                target_domains = set()
                for l in link_list:
                    try:
                        from urllib.parse import urlparse
                        target_domains.add(urlparse(l["target_url"]).netloc.lower())
                    except Exception:
                        pass
                outbound_urls = []
                for anchor, url in article_links:
                    try:
                        from urllib.parse import urlparse
                        netloc = urlparse(url).netloc.lower()
                        if netloc not in target_domains and '/api/v1/images/' not in url:
                            outbound_urls.append((anchor, url))
                    except Exception:
                        pass
                
                if outbound_urls:
                    verification = json.loads(execute_verify_urls([u for _, u in outbound_urls]))
                    dead_urls = {v["url"] for v in verification if not v.get("ok")}
                    if dead_urls:
                        # Remove dead links from article (replace with just the anchor text)
                        for anchor, url in outbound_urls:
                            if url in dead_urls:
                                article_content = article_content.replace(f'[{anchor}]({url})', anchor)
                        print(f"[article_writer] Removed {len(dead_urls)} dead links: {dead_urls}")
                
                # Post-generation: ensure ALL target links are present
                # If the model forgot to include them, use the LLM to weave them in naturally
                missing_links = []
                for link in link_list:
                    target_url = link["target_url"]
                    anchor_text = link["anchor_text"]
                    if target_url not in article_content:
                        missing_links.append(link)
                        print(f"[article_writer] Target link missing: [{anchor_text}]({target_url})")
                
                if missing_links:
                    # Ask the LLM to naturally integrate the missing links
                    missing_links_text = "\n".join([
                        f'- Anchor: "{l["anchor_text"]}" → URL: {l["target_url"]}'
                        for l in missing_links
                    ])
                    fix_prompt = f"""The following article is missing some required target links. Rewrite the article with these links woven in naturally — they should feel like genuine recommendations, not forced insertions. Do NOT use patterns like "For more, visit [X]" or "Check out [X]" at the end. Instead, integrate them into existing sentences or add a relevant sentence where they fit contextually.

MISSING LINKS:
{missing_links_text}

ARTICLE:
{article_content}

Return ONLY the updated article (TITLE: line + body). No preamble."""
                    try:
                        fix_response = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={
                                "x-api-key": api_key,
                                "anthropic-version": "2023-06-01",
                                "content-type": "application/json",
                            },
                            json={
                                "model": settings.anthropic_model,
                                "max_tokens": 4096,
                                "messages": [{"role": "user", "content": fix_prompt}],
                            },
                        )
                        if fix_response.status_code == 200:
                            fix_result = fix_response.json()
                            fix_text = ""
                            for block in fix_result.get("content", []):
                                if block.get("type") == "text":
                                    fix_text += block["text"]
                            fix_text = fix_text.strip()
                            # Verify the fix actually includes the missing links
                            all_fixed = all(l["target_url"] in fix_text for l in missing_links)
                            if all_fixed and "TITLE:" in fix_text:
                                article_content = "TITLE:" + fix_text.split("TITLE:", 1)[1].strip()
                                print(f"[article_writer] Successfully integrated {len(missing_links)} missing links via LLM")
                            else:
                                print(f"[article_writer] LLM fix didn't include all links, falling back")
                                # Last resort: simple but less ugly injection
                                for link in missing_links:
                                    paragraphs = article_content.split('\n\n')
                                    if len(paragraphs) >= 4:
                                        paragraphs[2] += f" [{link['anchor_text']}]({link['target_url']}) is worth checking out for anyone exploring this space."
                                        article_content = '\n\n'.join(paragraphs)
                                    else:
                                        article_content += f"\n\n[{link['anchor_text']}]({link['target_url']}) is worth checking out for anyone exploring this space.\n"
                    except Exception as e:
                        print(f"[article_writer] LLM link fix failed: {e}, using fallback")
                        for link in missing_links:
                            paragraphs = article_content.split('\n\n')
                            if len(paragraphs) >= 4:
                                paragraphs[2] += f" [{link['anchor_text']}]({link['target_url']}) is worth checking out for anyone exploring this space."
                                article_content = '\n\n'.join(paragraphs)
                            else:
                                article_content += f"\n\n[{link['anchor_text']}]({link['target_url']}) is worth checking out for anyone exploring this space.\n"

                # Extract title and summary for topic tracking
                title = _extract_title(article_content)
                topic_summary = _extract_topic_summary(article_content)
                
                # Save topic to prevent duplication
                article_topic = ArticleTopic(
                    id=str(uuid4()),
                    order_id=order_id,
                    domain_id=domain.id,
                    title=title,
                    topic_summary=topic_summary,
                )
                db.add(article_topic)
                
                # Generate images if not skipped
                image_results = []
                if not skip_images:
                    from .image_generator import (
                        extract_image_placeholders,
                        generate_article_images,
                        replace_image_placeholders,
                    )
                    import shutil as _shutil
                    from pathlib import Path as _Path

                    # Wipe old images so stale Pexels/previous files never survive a regeneration
                    old_img_dir = _Path(f"data/images/{order_id}")
                    if old_img_dir.exists():
                        _shutil.rmtree(old_img_dir)

                    image_descriptions = extract_image_placeholders(article_content)
                    if image_descriptions:
                        image_results = await generate_article_images(
                            order_id=order_id,
                            image_descriptions=image_descriptions,
                        )
                        # Replace placeholders with markdown images
                        article_content = replace_image_placeholders(article_content, image_results)

                # Final-pass deterministic brand enforcement.
                # This must run after any LLM rewrites (e.g., missing-link fixer), otherwise
                # brand requirements can be overwritten by later rewrite steps.
                if brand_mentions_body_count and required_brands:
                    final_title_line = ""
                    final_body_text = article_content
                    if "TITLE:" in article_content:
                        final_title_line = article_content.split("\n", 1)[0].replace("TITLE:", "").strip()
                        final_body_text = article_content.split("\n", 1)[1] if "\n" in article_content else ""

                    if brand_mentions_in_title and final_title_line:
                        if all(_count_phrase(final_title_line, b) == 0 for b in required_brands):
                            final_title_line = f"{required_brands[0]}: {final_title_line}"

                    for brand in required_brands:
                        current = _count_phrase(final_body_text, brand)
                        if current < brand_mentions_body_count:
                            missing = brand_mentions_body_count - current
                            filler = " ".join([brand] * missing)
                            final_body_text = f"{final_body_text}\n\n## Brand Spotlight\n{filler}."

                    if final_title_line:
                        article_content = f"TITLE: {final_title_line}\n{final_body_text}".strip()
                    else:
                        article_content = final_body_text.strip()
                
                # Apply nofollow rel attributes if configured
                article_content = _apply_nofollow(
                    article_content, link_list, order,
                )
                
                # Save final article with images
                order.article_content = article_content
                order.status = "content_ready"
                db.commit()
                db.refresh(order)

                return {
                    "success": True,
                    "order_id": order_id,
                    "article_content": article_content,
                    "word_count": len(article_content.split()),
                    "status": "content_ready",
                    "title": title,
                    "topic_summary": topic_summary,
                    "images": image_results,
                    "image_count": len(image_results),
                }

            # Feed tool results back
            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": tool_results})

    raise Exception("Article generation exceeded max iterations")


def _extract_title(article_content: str) -> str:
    """Extract title from article content."""
    lines = article_content.split("\n")
    for line in lines:
        if line.strip().startswith("TITLE:"):
            return line.replace("TITLE:", "").strip()
    return "Untitled Article"


def _extract_topic_summary(article_content: str) -> str:
    """Generate a brief topic summary from the article."""
    # Take first paragraph after title as summary
    lines = article_content.split("\n")
    in_content = False
    for line in lines:
        if line.strip().startswith("TITLE:"):
            in_content = True
            continue
        if in_content and line.strip() and not line.strip().startswith("#"):
            # Return first 200 chars of first paragraph
            return line.strip()[:200]
    return "No summary available"


def _apply_nofollow(
    article_content: str,
    link_list: List[Dict[str, str]],
    order,
) -> str:
    """Apply rel="nofollow" or rel="nofollow ugc" to links in the article.
    
    - nofollow_target: applies rel="nofollow" to our money links (target site URLs)
    - nofollow_resources: applies rel="nofollow ugc" to all other outbound links (authority/resource links)
    
    Converts markdown links to HTML <a> tags ONLY for links that need rel attributes.
    Links that don't need rel attributes stay as markdown.
    """
    nofollow_target = getattr(order, 'nofollow_target', False)
    nofollow_resources = getattr(order, 'nofollow_resources', False)
    
    if not nofollow_target and not nofollow_resources:
        return article_content
    
    # Build set of target domains/URLs for identification
    target_urls_normalized = set()
    for link in link_list:
        url = link.get("target_url", "")
        if url:
            # Normalize: lowercase, strip protocol and www
            norm = re_module.sub(r'^https?://', '', url.lower()).lstrip('www.').rstrip('/')
            target_urls_normalized.add(norm)
    
    def _is_target_link(url: str) -> bool:
        """Check if a URL is one of our target/money links."""
        norm = re_module.sub(r'^https?://', '', url.lower()).lstrip('www.').rstrip('/')
        for target in target_urls_normalized:
            if norm == target or norm.startswith(target + '/') or norm.startswith(target + '?'):
                return True
            if target.startswith(norm + '/') or target.startswith(norm + '?') or target == norm:
                return True
        return False
    
    def _replace_link(match):
        anchor = match.group(1)
        url = match.group(2)
        
        is_target = _is_target_link(url)
        
        if is_target and nofollow_target:
            return f'<a href="{url}" rel="nofollow">{anchor}</a>'
        elif not is_target and nofollow_resources:
            # Skip image URLs and internal references
            if '/api/v1/images/' in url or url.startswith('#'):
                return match.group(0)  # Keep as-is
            return f'<a href="{url}" rel="nofollow ugc">{anchor}</a>'
        else:
            return match.group(0)  # Keep as markdown
    
    # Replace markdown links: [text](url)
    # But NOT image placeholders: ![text](url)
    result = re_module.sub(
        r'(?<!!)\[([^\]]+)\]\((https?://[^)]+)\)',
        _replace_link,
        article_content,
    )
    
    return result


async def generate_articles_batch(
    order_ids: List[str],
    db: Session,
) -> Dict[str, Any]:
    """Generate articles for multiple orders in batch."""
    results = {"success": 0, "failed": 0, "errors": []}
    for order_id in order_ids:
        try:
            await generate_article(order_id, db)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"order_id": order_id, "error": str(e)})
    return results
