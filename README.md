# posthog-writer-agent

An MCP server that turns PostHog's documentation into something an AI coding agent can query directly, instead of guessing from stale training data.

PostHog's own job posting describes a **"Writer agent"**: a RAG (retrieval-augmented generation) system that maintains the company's docs. I built a small, working version of that same pattern against PostHog's real public documentation, to demonstrate that I've already solved the problem their Context Engineer role exists to solve, before being hired to do it. Primarily, this project is for PostHog's hiring team. A real secondary use case exists too: PostHog ships fast, and any AI coding agent building against it runs into a model whose training data lags behind the product. This server gives that agent a way to retrieve current, sourced documentation instead of guessing.

This project is independent and unofficial. PostHog did not build it, does not endorse it, and has no affiliation with it.

**The full build story, including three real bugs and the reasoning behind the chunking and retrieval design, is written up here: [dvoorhees.com — Building an MCP Server for PostHog's Documentation](https://dvoorhees.com/2026/07/29/building-an-mcp-server-for-posthog-documentation/).** This README covers how to use and run it.

---

## Try it now

The server is deployed and running, so trying it takes no setup:

- Landing page: [posthog-writer-agent.fly.dev](https://posthog-writer-agent.fly.dev/)
- Health check: [posthog-writer-agent.fly.dev/health](https://posthog-writer-agent.fly.dev/health)
- MCP endpoint: `https://posthog-writer-agent.fly.dev/mcp`

Connect it to Claude Code in one line:

```bash
claude mcp add --transport http posthog-writer-agent https://posthog-writer-agent.fly.dev/mcp
```

Any other MCP-compatible client (Claude Desktop, Cursor) connects the same way, pointing at the same URL. Once connected, ask your assistant something like:

> "How do PostHog feature flags handle identity before a user logs in?"

The assistant calls `search_posthog_docs` on this server and returns a sourced answer pulled from real PostHog documentation.

---

## What this is, and how it gets used

A search tool for PostHog's documentation, nothing more. It answers one kind of request: find the relevant PostHog doc content for a given question. Turning that content into a conversational answer is a separate job, handled by whichever AI assistant calls the server.

Nobody talks to the server directly. The sequence runs like this: someone's AI assistant is configured to know this server exists, either at the live Fly URL or, for local development, at `server.py` directly. The person asks an ordinary question. The assistant decides on its own that this server can help, calls one of three tools, and the server returns the relevant doc chunks. The assistant reads that text and writes an answer grounded in current PostHog docs.

MCP is an open standard. Anthropic created it, Claude Code and Claude Desktop support it, and so does Cursor. `server.py` contains no check for Claude specifically; point a different MCP client at it and it behaves identically. The Context Engineer job posting names coding agents, MCPs, and harnesses as things a candidate should have built and formed real opinions about, and MCP is also the mechanism PostHog uses internally to let AI agents interact with its own product.

OpenAI's role is narrow and specific: comparing "what's being asked" against "what's in the docs" requires meaning-based matching, which depends on embeddings. OpenAI's API generates those embeddings, once during setup for every cached doc chunk, and again on every tool call for the incoming query. It answers nothing itself; the connected MCP client does that part.

---

## What it covers

Three PostHog doc sections, deep enough to show the retrieval pattern holds up against real, substantial technical content: Feature Flags (overview and production best practices), Product Analytics (getting started and event schema management), and Session Replay (recording controls and trigger configuration).

---

## Tools

### `search_posthog_docs(query, max_results)`
General semantic search across all three doc sections. Best for open-ended questions.

### `get_configuration_guide(topic)`
Tuned toward step-by-step setup content. Retrieves five chunks instead of the default four, since configuration questions usually need more surrounding detail to be actionable.

### `explain_event_schema(aspect)`
Scoped to the Product Analytics schema management docs specifically: typed property groups, the CLI workflow, best practices. A question like "how does event schema work" gets its own entry point here, separate from general search.

---

## Architecture

```
docs_cache/*.md  →  ingest.py  →  chroma_store/ (local vector DB)
                    (OpenAI embeddings)
                                        ↓
                                  server.py (FastMCP)
                                        ↓
                    query embedded via OpenAI, matched against chroma_store
                                        ↓
                          Claude Code / Claude Desktop / any MCP client
                                        ↓
                              person gets a sourced answer
```

No external vector database service, no pipeline scraping PostHog's live site on a schedule. Docs were fetched once, cleaned, and cached locally as markdown in `docs_cache/`, then chunked and embedded by `ingest.py` into a local ChromaDB instance.

Chunking splits on Markdown `##` header boundaries first, with a character cap as a fallback for oversized sections. Embeddings run through OpenAI's `text-embedding-3-small`. ChromaDB runs in local persistent mode, keeping the whole thing dependency-light. The reasoning behind each of these choices, along with the mid-sentence chunking bug that shaped the final approach, is in the [build post](https://dvoorhees.com/2026/07/29/building-an-mcp-server-for-posthog-documentation/).

---

## Context window tradeoffs

Each tool call returns four or five chunks by default: four for `search_posthog_docs`, five for `get_configuration_guide`. Too few risks missing a valid answer; too many spends the calling agent's context budget on marginal results. For a doc set this size, a few dozen chunks total, four or five results reliably surfaces the right one. A much larger corpus would need a lower count or a reranking step.

---

## Running it yourself

The live deployment above is the fastest way to try this. What follows is for inspecting, modifying, or redeploying the code.

### Local setup

```bash
git clone https://github.com/d-voorhees/posthog-writer-agent.git
cd posthog-writer-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY in .env, then:
export OPENAI_API_KEY=your-key-here
python ingest.py
```

Ingestion runs in well under a minute. It reads `docs_cache/`, chunks it, embeds each chunk through the OpenAI API, and stores the result in a local `chroma_store/` directory.

### Running locally (stdio, for Claude Code, Claude Desktop, or any other MCP client)

```bash
python server.py
```

For Claude Code specifically:

```bash
OPENAI_API_KEY=your-key-here claude mcp add posthog-writer-agent -- python /full/path/to/posthog-writer-agent/server.py
```

### Running as a remote HTTP server

```bash
python server.py --http
```

Serves over streamable HTTP on the port set by the `PORT` environment variable, defaulting to 8000. The transport changes; the tools, retrieval logic, and OpenAI dependency stay identical to the local stdio version.

### Deployment (Fly.io)

The live server above runs on Fly.io, deployed the same way as [Bird by Bird](https://github.com/d-voorhees/bird-by-bird): free tier, with `min_machines_running = 1` to avoid cold starts. The `Dockerfile`, `fly.toml`, and `entrypoint.sh` in this repo are what run it.

```bash
fly launch --no-deploy   # review the generated config against fly.toml in this repo
fly secrets set OPENAI_API_KEY=your-key-here
fly deploy
```

No persistent Fly volume is attached. `entrypoint.sh` checks whether `chroma_store/` already exists and runs `ingest.py` on first boot if not, costing under a minute on a fresh deploy.

Fly runs more than one machine behind a single app by default, with no guaranteed session affinity between requests. FastMCP's HTTP transport tracks session state in memory per process by default, so a handshake landing on one machine followed by a tool call landing on another closes the connection. `server.py` sets `stateless_http=True` on the `FastMCP()` constructor to remove that dependency. The tradeoff: features that rely on a persistent session, resumable streaming connections across a reconnect, for instance, aren't available in this mode. For a documentation-lookup server where every tool call is independent, that cost is close to nothing; a server needing multi-turn state within a single client session would need a different fix, most likely session affinity configured at the load balancer instead.

---

## Limits

This is a demo-scale deployment, not production infrastructure, and it's built to fail safely rather than to fail expensively. A few things worth knowing before pointing something serious at it:

**No auth, no persistent storage.** `/mcp` is open — anyone with the URL can call it, by design, since the whole point is a one-line `claude mcp add`. `chroma_store/` isn't backed by a Fly volume, so it's rebuilt from `docs_cache/` on every fresh boot rather than persisted; the guardrails below share that same ephemeral tradeoff.

**Per-IP rate limit.** Each client IP is capped at `RATE_LIMIT_REQUESTS` calls to `/mcp` per `RATE_LIMIT_WINDOW_SECONDS` (default: 10 per 60s). Past that, the server returns `429` until the window rolls over. This bounds how fast any single source can hit the server; it does nothing against many different IPs hitting it at once, which is what the Fly concurrency cap below is for.

**Daily OpenAI budget.** Every tool call makes exactly one OpenAI embeddings call (`text-embedding-3-small`, capped at 300 input characters — there's no code path to a chat/completions call or a caller-chosen model). Total calls across all callers combined are capped at `DAILY_OPENAI_CALL_LIMIT` per day (default: 100). Past that, tools return a plain-language message explaining the server is at capacity instead of erroring out or silently failing. Because there's no persistent volume, this counter resets on restart/redeploy rather than holding a hard boundary across a full calendar day.

**Fly concurrency cap.** `fly.toml` caps each machine at 20 concurrent in-flight requests (soft) / 25 (hard) before the proxy queues or rejects further ones, independent of the per-IP limit above — this is what catches a burst from many different IPs at once rather than one repeat caller.

None of these are tuned for real production traffic; they're tuned to keep a demo project's blast radius, and its owner's OpenAI bill, small if the public URL ever gets hit harder than expected.

---

## Example queries

**Query:** "how does feature flag rollout percentage work"
Calls `search_posthog_docs` and returns chunks covering the SHA-1 hash formula and what "same inputs, same output" means for debugging flags.

**Query:** "session replay sampling"
Calls `search_posthog_docs` and returns chunks on the deterministic session-ID hashing behind sampling, and why the record decision stays fixed across page refreshes.

**Query:** "property groups"
Calls `explain_event_schema`, which filters to Product Analytics content specifically, and returns the property group creation and schema-attachment workflow.

All three ran end to end through Claude Code against a real OpenAI key and a populated ChromaDB instance.

---

## Stack

- Python 3.12
- FastMCP (`mcp[cli]==1.29.0`)
- OpenAI API (`text-embedding-3-small`)
- ChromaDB (local persistent mode)
- Fly.io (deployment)

A star on the repo helps others find it, if this saves you time building something similar.
# posthog-writer-agent
