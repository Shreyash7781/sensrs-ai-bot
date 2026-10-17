
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from urllib.parse import urlparse

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import errors


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / "backend" / ".env")

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "gemini-embedding-2"
)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. Check your .env file."
    )

client = genai.Client(api_key=API_KEY)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
MANIFEST_PATH = REPORTS_DIR / "page_manifest.json"
CHROMA_DIR = BASE_DIR / "chroma_db"

LIVE_COLLECTION = "sensrs_knowledge"
STAGING_COLLECTION = "sensrs_knowledge_staging"

chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)


def get_display_title(title, url):
    from urllib.parse import urlparse

    generic_titles = {
        "",
        "sensrs - iit ropar",
        "sensrs"
    }

    if title.strip().lower() not in generic_titles:
        return title.strip()

    path = urlparse(url).path.strip("/")

    if not path:
        return "SEnSRS Home"

    name = path.split("/")[-1]
    name = name.replace("-", " ").replace("_", " ")

    return name.title()



def normalize_url(url):
    """Normalize URLs for duplicate detection."""
    parts = urlsplit(url.strip())

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/").lower() or "/",
        parts.query,
        ""
    ))


def clean_text(text):
    """Clean common encoding errors and excessive whitespace."""
    replacements = {
        "â€™": "’",
        "â€˜": "‘",
        "â€œ": "“",
        "â€": "”",
        "â€“": "–",
        "â€”": "—",
        "Â ": " ",
        "\u00a0": " ",
        "\ufeff": ""
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def load_manifest():
    """Load valid, current crawl entries only."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        entries = json.load(file)

    if not isinstance(entries, list):
        raise ValueError(
            "page_manifest.json must contain a JSON list."
        )

    valid_entries = []
    seen_urls = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        filename = entry.get("file", "")
        url = entry.get("url", "").strip()
        status = entry.get("status")

        # Only use plain-text files listed in the manifest.
        if (
            not filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() != ".txt"
        ):
            continue

        if not url.startswith(("https://", "http://")):
            continue

        # Exclude failed pages and PDF URLs.
        if status != 200:
            continue

        if urlsplit(url).path.lower().endswith(".pdf"):
            continue

        # Avoid duplicate URLs, including case-only path variants.
        normalized = normalize_url(url)

        if normalized in seen_urls:
            print(f"[DUPLICATE URL SKIPPED] {url}")
            continue

        seen_urls.add(normalized)

        file_path = DATA_DIR / filename

        if not file_path.is_file():
            print(f"[MISSING FILE] {filename}")
            continue

        valid_entries.append({
            "file": filename,
            "title": (
                entry.get("title") or ""
            ).strip(),
            "url": url,
            "path": file_path,
            "characters": entry.get("characters", 0),
            "notes": entry.get("notes", "")
        })

    if not valid_entries:
        raise RuntimeError(
            "No valid pages found in the crawl manifest. "
            "Existing knowledge has not been changed."
        )

    return valid_entries


def create_embedding(text, max_retries=5):
    """Generate Gemini embeddings with rate-limit retries."""
    for attempt in range(max_retries):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text
            )

            if not response.embeddings:
                raise RuntimeError(
                    "Gemini returned no embedding."
                )

            return response.embeddings[0].values

        except errors.ClientError as exc:
            message = str(exc).upper()

            is_rate_limit = (
                "429" in message
                or "RESOURCE_EXHAUSTED" in message
            )

            if not is_rate_limit:
                raise

            if attempt == max_retries - 1:
                raise

            wait_seconds = (attempt + 1) * 5

            print(
                f"[RATE LIMIT] Waiting {wait_seconds}s "
                f"before retry {attempt + 2}/{max_retries}"
            )

            time.sleep(wait_seconds)

    raise RuntimeError("Embedding generation failed.")


def create_chunks(text, chunk_size=1800, overlap=300):
    """Split text while preserving paragraph boundaries."""
    text = text.strip()

    if not text:
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if len(paragraph) <= chunk_size:
            if len(current) + len(paragraph) + 2 <= chunk_size:
                current += ("\n\n" if current else "") + paragraph
            else:
                if current:
                    chunks.append(current)

                current = paragraph

        else:
            if current:
                chunks.append(current)
                current = ""

            start = 0

            while start < len(paragraph):
                end = start + chunk_size
                chunks.append(paragraph[start:end].strip())

                if end >= len(paragraph):
                    break

                start = end - overlap

    if current:
        chunks.append(current)

    return chunks


def read_page(entry):
    """Read a manifest-listed text file and add page context."""
    raw_text = entry["path"].read_text(encoding="utf-8")
    raw_text = clean_text(raw_text)

    # Remove crawler headers because the authoritative metadata
    # is added below from page_manifest.json.
    raw_text = re.sub(
        r"(?im)^PAGE_TITLE:.*$",
        "",
        raw_text
    )

    raw_text = re.sub(
        r"(?im)^PAGE_URL:.*$",
        "",
        raw_text
    )

    raw_text = clean_text(raw_text)

    title = entry["title"] or entry["url"]

    page_context = (
        "SEnSRS Website Knowledge\n"
        f"Page Title: {title}\n"
        f"Page URL: {entry['url']}\n\n"
    )

    return page_context + raw_text


def switch_to_new_collection(staging):
    """
    Switch collections after successful ingestion.
    Keep the previous collection under a backup name.
    """
    existing_names = {
        collection.name
        for collection in chroma_client.list_collections()
    }

    backup_name = (
        "sensrs_backup_"
        + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    )

    old_collection_backed_up = False

    if LIVE_COLLECTION in existing_names:
        old_collection = chroma_client.get_collection(
            LIVE_COLLECTION
        )

        old_collection.modify(name=backup_name)
        old_collection_backed_up = True

        print(f"[BACKUP] Previous collection: {backup_name}")

    try:
        staging.modify(name=LIVE_COLLECTION)

    except Exception:
        # Attempt to restore the previous live collection.
        if old_collection_backed_up:
            try:
                chroma_client.get_collection(
                    backup_name
                ).modify(name=LIVE_COLLECTION)

                print("[ROLLBACK] Previous collection restored.")

            except Exception as rollback_error:
                print(
                    "[IMPORTANT] Automatic rollback failed. "
                    f"Previous collection is still named "
                    f"{backup_name}. Error: {rollback_error}"
                )

        raise


def main():
    print("=" * 60)
    print("SEnSRS WEBSITE KNOWLEDGE INGESTION")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print("=" * 60)

    entries = load_manifest()

    print(f"Valid manifest pages: {len(entries)}")

    # The staging collection can be safely rebuilt because it is
    # not the collection used by the live chatbot.
    try:
        chroma_client.delete_collection(STAGING_COLLECTION)
        print("[INFO] Removed previous staging collection.")
    except Exception:
        pass

    staging = chroma_client.create_collection(
        name=STAGING_COLLECTION,
        metadata={"description": "SEnSRS knowledge staging"}
    )

    total_chunks = 0
    failed_pages = []

    try:
        for page_number, entry in enumerate(entries, start=1):
            print(
                f"\n[{page_number}/{len(entries)}] "
                f"{entry['title'] or entry['url']}"
            )
            print(f"URL: {entry['url']}")

            try:
                page_text = read_page(entry)
                chunks = create_chunks(page_text)

                if not chunks:
                    print("[SKIPPED] Page contains no text.")
                    continue

                print(f"Chunks: {len(chunks)}")

                for index, chunk in enumerate(chunks):
                    embedding = create_embedding(chunk)

                    staging.add(
                        ids=[
                            f"{entry['path'].stem}_{index}"
                        ],
                        documents=[chunk],
                        embeddings=[embedding],
                        metadatas=[{
                            "source": entry["file"],
                            "title": get_display_title(
    entry["title"],
    entry["url"]
),
                            "url": entry["url"],
                            "chunk_index": index
                        }]
                    )

                    total_chunks += 1
                    time.sleep(0.5)

                print("[OK] Page ingested.")

            except Exception as exc:
                failed_pages.append({
                    "url": entry["url"],
                    "error": str(exc)
                })

                print(f"[FAILED] {entry['url']}: {exc}")
                raise

        if total_chunks == 0:
            raise RuntimeError(
                "No chunks were created. Live collection unchanged."
            )

        if failed_pages:
            raise RuntimeError(
                "One or more pages failed. "
                "Live collection unchanged."
            )

        print("\n" + "=" * 60)
        print("STAGING INGESTION COMPLETED")
        print(f"Pages considered: {len(entries)}")
        print(f"Chunks created: {total_chunks}")
        print(f"Staging collection count: {staging.count()}")
        print("=" * 60)

        # Only switch after every page was processed successfully.
        switch_to_new_collection(staging)

        live = chroma_client.get_collection(LIVE_COLLECTION)

        print("\nSUCCESS: New knowledge collection is active.")
        print(f"Live collection: {LIVE_COLLECTION}")
        print(f"Live chunk count: {live.count()}")
        print(
            "The previous collection, if one existed, "
            "has been retained as a backup."
        )

    except Exception:
        print("\n[ERROR] Ingestion did not complete successfully.")
        print(
            "The existing live collection was not intentionally "
            "deleted. Inspect the error before trying again."
        )
        raise


if __name__ == "__main__":
    main()
