import os
import httpx
import anthropic
from schemas import BusinessProfile, AnalysisReport

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

RESEARCH_SYSTEM = (
    "You are a market researcher for small, in-person local businesses. Use web search to find "
    "real nearby competitors and what customers say about them (reviews, menus, prices, wait times). "
    "Only report facts you found; say 'unknown' otherwise. Keep notes compact and include source URLs."
)

REPORT_SYSTEM = (
    "You turn raw competitor research into an honest, practical report for a small business owner. "
    "Do not invent data. Recommendations must cite evidence from the research. Prefer few, "
    "concrete, high-impact actions over generic advice."
)


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def tavily_research(p: BusinessProfile) -> str:
    """Fast path: a few Tavily searches (1 credit each), concatenated for Claude to analyze."""
    key = os.environ["TAVILY_API_KEY"]
    where = p.neighborhood
    queries = [
        f"best {p.category} near {where} menu prices",
        f"{p.category} {where} reviews complaints long wait",
        f"{p.category} {where} reviews what customers love",
        f"{p.category} trends {where} 2026",
    ]
    chunks = []
    for q in queries:
        r = httpx.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": q, "search_depth": "basic", "max_results": 6, "include_answer": True},
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        chunks.append(f"## Query: {q}\nSummary: {d.get('answer')}")
        for x in d.get("results", []):
            chunks.append(f"- {x['title']} ({x['url']}): {x['content'][:600]}")
    return "\n".join(chunks)


def research(client: anthropic.Anthropic, p: BusinessProfile) -> str:
    prompt = (
        f"Business: {p.name} ({p.category}) in {p.neighborhood}. "
        f"Their avg price: {p.avg_price or 'unknown'}; avg wait: {p.avg_wait_minutes or 'unknown'} min. "
        f"Owner notes: {p.notes or 'none'}.\n\n"
        "Find 4-6 direct competitors within walking distance / same neighborhood. For each: price range, "
        "typical wait, rating, strengths, recurring customer complaints, and source URLs. "
        "Then list local market trends for this category."
    )
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    for _ in range(5):  # resume if the server-side tool loop pauses
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=RESEARCH_SYSTEM,
            tools=tools,
            output_config={"effort": "low"},
            messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            return _text(resp)
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    return _text(resp)


def build_report(client: anthropic.Anthropic, p: BusinessProfile, notes: str) -> AnalysisReport:
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=REPORT_SYSTEM,
        output_config={"effort": "medium"},
        messages=[{
            "role": "user",
            "content": f"Business profile:\n{p.model_dump_json(indent=2)}\n\nResearch notes:\n{notes}",
        }],
        output_format=AnalysisReport,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"Claude returned no report (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def analyze(p: BusinessProfile) -> AnalysisReport:
    client = anthropic.Anthropic()
    notes = tavily_research(p) if os.getenv("TAVILY_API_KEY") else research(client, p)
    return build_report(client, p, notes)
