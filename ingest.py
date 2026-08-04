"""
Ingest PostHog docs into a local ChromaDB collection.

Reads markdown files from docs_cache/, chunks them by section boundary
(splitting further only when a section is too large), embeds each chunk
with OpenAI's text-embedding-3-small, and stores the result in a local
persistent ChromaDB instance.

Usage:
    python ingest.py
"""

import os
import re
import glob
import chromadb
from openai import OpenAI

DOCS_CACHE_DIR = os.path.join(os.path.dirname(__file__), "docs_cache")
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
COLLECTION_NAME = "posthog_docs"
EMBEDDING_MODEL = "text-embedding-3-small"

# Target chunk size in characters. This is a rough proxy for tokens
# (roughly 4 chars/token for English text), chosen because these source
# docs are already well-structured Markdown with clear ## section
# boundaries, so splitting on structure first gets us naturally-sized,
# semantically coherent chunks most of the time. The character cap only
# kicks in for the rare oversized section (e.g., the best-practices doc,
# where several ### subsections under one ## header add up).
MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP_CHARS = 200


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a simple YAML frontmatter block from the rest of the doc."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter_raw, body = match.groups()
    frontmatter = {}
    for line in frontmatter_raw.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def split_by_headers(body: str) -> list[str]:
    """Split a doc body into sections at ## header boundaries.

    Keeps the ## header line attached to its own section so each chunk
    is self-describing even out of context.
    """
    sections = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    return [s.strip() for s in sections if s.strip()]


def split_oversized_section(section: str) -> list[str]:
    """Fall back to character-based splitting with overlap for sections
    that exceed MAX_CHUNK_CHARS, splitting on paragraph boundaries where
    possible rather than mid-sentence.
    """
    if len(section) <= MAX_CHUNK_CHARS:
        return [section]

    paragraphs = section.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= MAX_CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # carry a small overlap forward so context isn't lost at the seam
            overlap = current[-CHUNK_OVERLAP_CHARS:] if current else ""
            current = f"{overlap}\n\n{para}" if overlap else para

    if current:
        chunks.append(current)

    return chunks


def chunk_document(filepath: str) -> list[dict]:
    """Chunk a single cached doc file into a list of chunk records."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    frontmatter, body = parse_frontmatter(raw)
    sections = split_by_headers(body)

    chunks = []
    for section in sections:
        for piece in split_oversized_section(section):
            chunks.append({
                "text": piece,
                "title": frontmatter.get("title", os.path.basename(filepath)),
                "source_url": frontmatter.get("source_url", ""),
                "section": frontmatter.get("section", ""),
            })
    return chunks


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with OpenAI's embedding API."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is required. "
            "Copy .env.example to .env and fill in your key, "
            "or export it directly before running this script."
        )

    openai_client = OpenAI(api_key=api_key)
    chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    # Recreate the collection each run so re-ingesting is idempotent
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = chroma_client.create_collection(COLLECTION_NAME)

    doc_files = sorted(glob.glob(os.path.join(DOCS_CACHE_DIR, "*.md")))
    if not doc_files:
        raise RuntimeError(f"No .md files found in {DOCS_CACHE_DIR}")

    all_chunks = []
    for filepath in doc_files:
        chunks = chunk_document(filepath)
        print(f"{os.path.basename(filepath)}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\nTotal chunks: {len(all_chunks)}")
    print(f"Embedding with {EMBEDDING_MODEL}...")

    texts = [c["text"] for c in all_chunks]
    embeddings = embed_texts(openai_client, texts)

    collection.add(
        ids=[f"chunk_{i}" for i in range(len(all_chunks))],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "title": c["title"],
                "source_url": c["source_url"],
                "section": c["section"],
            }
            for c in all_chunks
        ],
    )

    print(f"\nIngested {len(all_chunks)} chunks into '{COLLECTION_NAME}' "
          f"at {CHROMA_PERSIST_DIR}")


if __name__ == "__main__":
    main()
