"""
posthog_writer_mcp: an MCP server that serves PostHog documentation to
agent clients via semantic search.

This is a small, working instance of what PostHog's own job posting
calls a "Writer agent": a RAG-powered agent system that maintains and
serves documentation. It covers three doc sections (Feature Flags,
Product Analytics, Session Replay) as a scoped demonstration, not a
full-site replica.

Run locally (stdio, for use with Claude Desktop/Claude Code):
    python server.py

Run as a remote HTTP server (for deployment, e.g. on Fly.io):
    python server.py --http
"""

import os
import sys
import json
import time
import threading
from collections import defaultdict, deque
import chromadb
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
COLLECTION_NAME = "posthog_docs"
EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_RESULT_COUNT = 4

# Every /mcp request that reaches a tool triggers one OpenAI embeddings
# call. There's no auth in front of this server (it's meant to be
# connected to with one command, per the README), so the only thing
# standing between a scripted flood and steady OpenAI spend is this
# limit. Bounds per client IP, not globally, so one abusive caller
# can't degrade the server for everyone else.
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", 10))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))

# Host/port are set on the FastMCP constructor itself in this SDK version,
# not passed to .run(). These only take effect for the HTTP transport;
# stdio mode ignores them. Binding 0.0.0.0 rather than the 127.0.0.1
# default is required for Fly (or any container) to route external
# traffic to the process at all.
#
# stateless_http=True is required for this specific deployment: Fly runs
# more than one machine behind a single app, with no guaranteed session
# affinity between requests. Without this flag, FastMCP tracks MCP
# session state in memory per-process. If the "initialize" handshake
# lands on one machine and the follow-up "tools/list" call gets routed
# to a different machine, that machine has no record of the session and
# closes the connection (MCP error -32000). Stateless mode avoids relying
# on any server-side session state surviving between requests.
mcp = FastMCP(
    "posthog_writer_mcp",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    stateless_http=True,
)


# ─── Landing page and health check ─────────────────────────────────────
# FastMCP serves the MCP protocol at /mcp, but a human visitor hitting
# the root URL in a browser would otherwise see a 404. This page tells
# them what they're looking at and how to connect.

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>posthog-writer-agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', -apple-system, system-ui, sans-serif; max-width: 720px; margin: 0 auto; padding: 40px 24px 60px; line-height: 1.65; color: #111; background: #fafafa; }
  .header { margin-bottom: 1rem; }
  .byline { font-size: 0.85rem; color: #666; margin-bottom: 0.6rem; }
  .byline a { color: #555; text-decoration: underline; text-underline-offset: 2px; }
  h1 { font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.4rem; }
  .tagline { font-size: 1.05rem; color: #444; margin-bottom: 0; }
  .status-bar { display: inline-flex; align-items: center; gap: 8px; background: #e8f5e9; border: 1px solid #c8e6c9; border-radius: 6px; padding: 2px 14px; font-size: 0.85rem; color: #2e7d32; margin: 0 0 1.2rem; }
  .status-dot { width: 8px; height: 8px; background: #4caf50; border-radius: 50%; display: inline-block; }
  .status-bar a { color: #2e7d32; text-decoration: underline; text-underline-offset: 2px; }
  section { margin-bottom: 2rem; }
  h2 { font-size: 1rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #888; margin-bottom: 0.8rem; }
  p { margin-bottom: 0.8rem; }
  pre { background: #1a1a1a; color: #e0e0e0; padding: 14px 18px; border-radius: 8px; overflow-x: auto; font-size: 0.88rem; margin: 0.8rem 0; }
  pre code { background: none; padding: 0; color: inherit; }
  code { background: #eee; padding: 2px 7px; border-radius: 4px; font-size: 0.88rem; }
  .tool-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; }
  .tool-name { font-weight: 600; font-family: 'Inter', monospace; font-size: 0.95rem; color: #1a1a1a; }
  .tool-desc { font-size: 0.9rem; color: #555; margin-top: 4px; }
  .queries { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 18px 20px; }
  .query { font-size: 0.95rem; color: #333; padding: 6px 0; }
  .query + .query { border-top: 1px solid #f0f0f0; padding-top: 10px; margin-top: 6px; }
  .query em { font-style: italic; color: #888; font-size: 0.85rem; }
  .footer { margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #e0e0e0; font-size: 0.85rem; color: #888; }
  .footer a { color: #555; text-decoration: underline; text-underline-offset: 2px; }
  a { color: #1a56db; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>

<div class="status-bar">
  <span class="status-dot"></span>
  Live and accepting connections &middot; <a href="/health">check health</a>
</div>

<div class="header">
  <h1>posthog-writer-agent</h1>
  <p class="byline">Built by <a href="https://github.com/d-voorhees">D. Voorhees</a></p>
  <p class="tagline">An MCP server that gives AI coding agents accurate, sourced answers from PostHog's documentation.</p>
</div>

<section>
  <p>This server indexes PostHog's Feature Flags, Product Analytics, and Session Replay documentation and serves it to any MCP-compatible AI tool. When your coding agent needs to know how PostHog works, it queries this server and gets current, sourced doc content instead of guessing from stale training data.</p>
</section>

<section>
  <h2>Connect</h2>
  <p>Point any MCP client (Claude Code, Claude Desktop, Cursor) at:</p>
  <pre><code>https://posthog-writer-agent.fly.dev/mcp</code></pre>
  <p>For Claude Code:</p>
  <pre><code>claude mcp add --transport http posthog-writer-agent https://posthog-writer-agent.fly.dev/mcp</code></pre>
</section>

<section>
  <h2>Tools</h2>
  <div class="tool-card">
    <div class="tool-name">search_posthog_docs</div>
    <div class="tool-desc">Semantic search across all three doc sections. Best for open-ended questions about how PostHog works.</div>
  </div>
  <div class="tool-card">
    <div class="tool-name">get_configuration_guide</div>
    <div class="tool-desc">Step-by-step setup content for a named topic. Retrieves more context per call since configuration questions need surrounding detail.</div>
  </div>
  <div class="tool-card">
    <div class="tool-name">explain_event_schema</div>
    <div class="tool-desc">PostHog's event schema management: typed property groups, the CLI workflow, and best practices.</div>
  </div>
</section>

<section>
  <h2>Try asking your agent</h2>
  <div class="queries">
    <div class="query">"How do PostHog feature flags handle identity before a user logs in?"<br><em>Calls search_posthog_docs, returns the hash-based bucketing explanation and identity resolution guidance.</em></div>
    <div class="query">"How does PostHog decide which sessions to record when I use sampling?"<br><em>Calls search_posthog_docs, returns the deterministic session-ID hashing mechanism and trigger group composition.</em></div>
    <div class="query">"How do PostHog event schema property groups work?"<br><em>Calls explain_event_schema, returns the property group creation workflow, CLI download steps, and typed client usage.</em></div>
  </div>
</section>

<div class="footer">
  <a href="https://github.com/d-voorhees/posthog-writer-agent">Source on GitHub</a> &middot; Independent project, not affiliated with PostHog
</div>

</body>
</html>"""


@mcp.custom_route("/", methods=["GET"])
async def landing_page(request: Request) -> HTMLResponse:
    return HTMLResponse(LANDING_HTML)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "posthog_writer_mcp"})


_openai_client: OpenAI | None = None
_chroma_collection = None

# Aggregate ceiling across every caller combined, distinct from the
# per-IP rate limiter above: that one bounds how fast one source can
# hit the server, this bounds how much OpenAI spend the day can add up
# to regardless of how many different sources contribute. Same
# ephemeral-storage tradeoff as chroma_store noted in entrypoint.sh —
# no volume is attached, so this resets on restart/redeploy rather
# than surviving as a hard per-calendar-day cap.
DAILY_OPENAI_CALL_LIMIT = int(os.environ.get("DAILY_OPENAI_CALL_LIMIT", 100))


class _DailyBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self._lock = threading.Lock()
        self._day: str | None = None
        self._count = 0

    def try_consume(self) -> bool:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            if today != self._day:
                self._day = today
                self._count = 0
            if self._count >= self.limit:
                return False
            self._count += 1
            return True


_daily_budget = _DailyBudget(DAILY_OPENAI_CALL_LIMIT)


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is required")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        try:
            _chroma_collection = client.get_collection(COLLECTION_NAME)
        except Exception as e:
            raise RuntimeError(
                f"Could not load collection '{COLLECTION_NAME}'. "
                f"Have you run `python ingest.py` yet? Original error: {e}"
            )
    return _chroma_collection


def _embed_query(query: str) -> list[float]:
    if not _daily_budget.try_consume():
        raise RuntimeError(
            f"This server has hit its daily usage limit "
            f"({DAILY_OPENAI_CALL_LIMIT} queries/day) and isn't accepting "
            f"new queries until 00:00 UTC. This cap exists to keep the "
            f"server's OpenAI usage bounded — try again after the reset."
        )
    client = _get_openai_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    return response.data[0].embedding


def _query_docs(query: str, n_results: int = DEFAULT_RESULT_COUNT, section_filter: str | None = None) -> list[dict]:
    collection = _get_collection()
    query_embedding = _embed_query(query)

    where_clause = {"section": section_filter} if section_filter else None
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_clause,
    )

    hits = []
    for i in range(len(results["documents"][0])):
        hits.append({
            "text": results["documents"][0][i],
            "title": results["metadatas"][0][i].get("title", ""),
            "source_url": results["metadatas"][0][i].get("source_url", ""),
            "section": results["metadatas"][0][i].get("section", ""),
            "distance": results["distances"][0][i] if "distances" in results else None,
        })
    return hits


def _format_hits_markdown(hits: list[dict]) -> str:
    if not hits:
        return "No relevant results found in the indexed PostHog docs."

    parts = []
    for hit in hits:
        parts.append(
            f"### {hit['title']}\n"
            f"Source: {hit['source_url']}\n\n"
            f"{hit['text']}\n"
        )
    return "\n---\n\n".join(parts)


# ─── Tool input models ─────────────────────────────────────────────────

class SearchDocsInput(BaseModel):
    """Input for searching PostHog documentation."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Natural-language search query, e.g. 'how does flag rollout percentage work'",
        min_length=1,
        max_length=300,
    )
    max_results: int = Field(
        default=DEFAULT_RESULT_COUNT,
        description="Maximum number of matching chunks to return",
        ge=1,
        le=10,
    )


class ConfigGuideInput(BaseModel):
    """Input for retrieving a configuration guide on a named topic."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    topic: str = Field(
        ...,
        description=(
            "Topic to get a configuration guide for, e.g. 'feature flags', "
            "'session replay recording controls', 'product analytics schema'"
        ),
        min_length=1,
        max_length=200,
    )


class EventSchemaInput(BaseModel):
    """Input for explaining PostHog's event schema management model."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    aspect: str = Field(
        default="overview",
        description=(
            "Which aspect of event schema management to explain, e.g. "
            "'creating events', 'property groups', 'typed events', or 'overview'"
        ),
        max_length=200,
    )


# ─── Tools ──────────────────────────────────────────────────────────────

@mcp.tool(
    name="search_posthog_docs",
    annotations={
        "title": "Search PostHog Documentation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def search_posthog_docs(params: SearchDocsInput) -> str:
    """Semantic search across the indexed PostHog documentation.

    Covers Feature Flags, Product Analytics, and Session Replay. Returns
    the most relevant chunks with source attribution so an agent can
    ground its answer in current PostHog documentation rather than
    relying on potentially stale training data.

    Args:
        params (SearchDocsInput): query text and max_results (1-10)

    Returns:
        str: Markdown-formatted matching chunks with source URLs, or a
        message indicating no relevant results were found.
    """
    try:
        hits = _query_docs(params.query, n_results=params.max_results)
        return _format_hits_markdown(hits)
    except Exception as e:
        return f"Error searching docs: {e}"


@mcp.tool(
    name="get_configuration_guide",
    annotations={
        "title": "Get PostHog Configuration Guide",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_configuration_guide(params: ConfigGuideInput) -> str:
    """Retrieve a configuration guide for a named PostHog topic.

    Unlike search_posthog_docs, this is tuned toward step-by-step setup
    content (e.g., "how do I set this up") rather than general Q&A. It
    biases retrieval toward chunks tagged as configuration-relevant by
    requesting more results and letting the caller see full context.

    Args:
        params (ConfigGuideInput): the topic to retrieve a guide for

    Returns:
        str: Markdown-formatted guide content with source URLs, or a
        message indicating no relevant results were found.
    """
    try:
        hits = _query_docs(params.topic, n_results=5)
        return _format_hits_markdown(hits)
    except Exception as e:
        return f"Error retrieving configuration guide: {e}"


@mcp.tool(
    name="explain_event_schema",
    annotations={
        "title": "Explain PostHog Event Schema",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def explain_event_schema(params: EventSchemaInput) -> str:
    """Explain how PostHog's event schema management works.

    Scoped specifically to the Product Analytics schema management
    docs (typed property groups, the CLI workflow, best practices),
    rather than general product analytics search.

    Args:
        params (EventSchemaInput): which aspect to explain

    Returns:
        str: Markdown-formatted explanation with source URLs.
    """
    try:
        query = f"event schema management {params.aspect}"
        hits = _query_docs(query, n_results=4, section_filter="product-analytics")
        return _format_hits_markdown(hits)
    except Exception as e:
        return f"Error explaining event schema: {e}"


# ─── Rate limiting ──────────────────────────────────────────────────────
# Plain ASGI middleware rather than Starlette's BaseHTTPMiddleware:
# BaseHTTPMiddleware buffers the whole downstream response to re-emit
# it, which fights with the streamable-http transport's own
# request/response handling. This only inspects headers and, if under
# the limit, hands the connection straight to the app untouched.

class RateLimitMiddleware:
    def __init__(self, app, path: str, limit: int, window_seconds: float):
        self.app = app
        self.path = path
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _client_ip(self, scope) -> str:
        headers = dict(scope.get("headers") or [])
        # Fly sets Fly-Client-IP to the real client, unspoofable from
        # outside Fly's edge. Fall back to X-Forwarded-For, then the
        # raw ASGI client tuple for local/non-Fly runs.
        fly_ip = headers.get(b"fly-client-ip")
        if fly_ip:
            return fly_ip.decode()
        forwarded = headers.get(b"x-forwarded-for")
        if forwarded:
            return forwarded.decode().split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        client_ip = self._client_ip(scope)
        now = time.monotonic()

        with self._lock:
            hits = self._hits[client_ip]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            limited = len(hits) >= self.limit
            if not limited:
                hits.append(now)

        if limited:
            response = JSONResponse(
                {
                    "error": "rate_limited",
                    "message": (
                        f"Too many requests from this IP: limit is "
                        f"{self.limit} per {int(self.window_seconds)}s. "
                        f"Try again shortly."
                    ),
                },
                status_code=429,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


if __name__ == "__main__":
    if "--http" in sys.argv:
        import uvicorn

        app = mcp.streamable_http_app()
        app.add_middleware(
            RateLimitMiddleware,
            path=mcp.settings.streamable_http_path,
            limit=RATE_LIMIT_REQUESTS,
            window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        )
        uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port)
    else:
        mcp.run()
