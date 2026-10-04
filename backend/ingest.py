import os
import re
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")

# Gemini
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = BASE_DIR / "chroma_db"
SOURCE_INFO = {
    "home.txt": {
        "title": "SEnSRS Home",
        "url": "https://sensrs.com/"
    },
    "about.txt": {
        "title": "About Us",
        "url": "https://sensrs.com/about-us/"
    },
    "vision_mission.txt": {
        "title": "Vision & Mission",
        "url": "https://sensrs.com/visionandmission/"
    },
    "internships.txt": {
        "title": "Internships",
        "url": "https://sensrs.com/internship/"
    },
    "phd.txt": {
        "title": "PhD Programme",
        "url": "https://sensrs.com/phd-programme/"
    },
    "opportunities.txt": {
        "title": "Opportunities",
        "url": "https://sensrs.com/opportunities/"
    },
    "policies.txt": {
        "title": "Policies",
        "url": "https://sensrs.com/policy/"
    },
    "services.txt": {
        "title": "Consultancy Services",
        "url": "https://sensrs.com/consultancy-services/"
    },
    "drone_services.txt": {
        "title": "Drone Mapping & Surveying",
        "url": "https://sensrs.com/consultancy-services/drone-services/"
    },
    "dgps_services.txt": {
        "title": "DGPS Surveying",
        "url": "https://sensrs.com/consultancy-services/dgps-service/"
    },
    "bathymetry_services.txt": {
        "title": "Bathymetry Survey",
        "url": "https://sensrs.com/consultancy-services/bathymetry-survey/"
    },
    "tls_services.txt": {
        "title": "Terrestrial Laser Scanning",
        "url": "https://sensrs.com/consultancy-services/tls-survey/"
    },
       "dashboard_development.txt": {
    "title": "Dashboard & Analytics",
    "url": "https://sensrs.com/consultancy-services/dashboards-analytics/"
},

"hyperspectral_services.txt": {
    "title": "Hyperspectral Sensor",
    "url": "https://sensrs.com/consultancy-services/hyperspectral-sensor/"
},

"web_development.txt": {
    "title": "Web Development",
    "url": "https://sensrs.com/consultancy-services/web-development/"
},

"app_development.txt": {
    "title": "App Development",
    "url": "https://sensrs.com/consultancy-services/app-development/"
},

"ip_services.txt": {
    "title": "Intellectual Property Services",
    "url": "https://sensrs.com/consultancy-services/ip-services/"
},

"projects.txt": {
    "title": "Projects",
    "url": "https://sensrs.com/projects/"
},

"publications.txt": {
    "title": "Publications",
    "url": "https://sensrs.com/publications/"
},

"events.txt": {
    "title": "Events",
    "url": "https://sensrs.com/events/"
},

"gallery.txt": {
    "title": "Gallery",
    "url": "https://sensrs.com/photo-gallery/"
},

"video_gallery.txt": {
    "title": "Video Gallery",
    "url": "https://sensrs.com/video-gallery/"
},

"press_news.txt": {
    "title": "Press and News",
    "url": "https://sensrs.com/press-and-news/"
},

"newsletter.txt": {
    "title": "Newsletter",
    "url": "https://sensrs.com/newsletter/"
},

"contact.txt": {
    "title": "Contact",
    "url": "https://sensrs.com/contact/"
},
}

# ChromaDB
chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)


def create_embedding(text, max_retries=5):
    """
    Generate embedding with retry logic and exponential backoff to handle rate limits.
    """
    for attempt in range(max_retries):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text
            )
            return response.embeddings[0].values
        except errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = (attempt + 1) * 5
                print(f"\n    [Rate limit hit. Waiting {wait_time}s before retrying (attempt {attempt + 1}/{max_retries})...]")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError(f"Failed to generate embedding after {max_retries} retries due to rate limits.")


def create_chunks(text, chunk_size=1800, overlap=300):
    """
    Create chunks while preserving paragraph/section boundaries.
    """

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

        # Add paragraph to current chunk if it fits
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current += ("\n\n" if current else "") + paragraph

        else:
            if current:
                chunks.append(current)

            # If a single paragraph is too large, split it
            if len(paragraph) > chunk_size:
                start = 0

                while start < len(paragraph):
                    end = start + chunk_size
                    chunks.append(paragraph[start:end].strip())

                    if end >= len(paragraph):
                        break

                    start = end - overlap

                current = ""
            else:
                current = paragraph

    if current:
        chunks.append(current)

    return chunks

def main():
    print(f"Starting SEnSRS knowledge ingestion (Model: {EMBEDDING_MODEL})...")

    files = sorted(list(DATA_DIR.glob("*.txt")))

    if not files:
        print("No .txt files found in data directory.")
        return

    # Reset collection to ensure dimensionality matches current embedding model
    try:
        chroma_client.delete_collection("sensrs_knowledge")
        print("Reset existing ChromaDB collection.")
    except Exception:
        pass

    collection = chroma_client.get_or_create_collection(
        name="sensrs_knowledge"
    )

    total_chunks = 0

    for file_path in files:
        print(f"\nProcessing: {file_path.name}")

        text = file_path.read_text(encoding="utf-8").strip()

        source_info = SOURCE_INFO.get(
            file_path.name,
            {
                "title": file_path.stem.replace("_", " ").title(),
                "url": ""
            }
        )

        page_context = f"""
SEnSRS Website Page
Title: {source_info["title"]}
URL: {source_info["url"]}

"""

        text = page_context + text

        chunks = create_chunks(text)
        print(f"  Found {len(chunks)} chunks.")

        for index, chunk in enumerate(chunks):
            embedding = create_embedding(chunk)

            collection.add(
                ids=[f"{file_path.stem}_{index}"],
                documents=[chunk],
                embeddings=[embedding],
                metadatas=[{
                    "source": file_path.name,
                    "title": source_info["title"],
                    "url": source_info["url"]
                }]
            )

            total_chunks += 1
            preview = chunk.replace("\n", " ")[:60]
            print(f"  Added chunk {index + 1}/{len(chunks)}: {preview}...")

            # Small delay to stay comfortably under API rate limits
            time.sleep(0.5)

    print("\n--------------------------------")
    print("Ingestion completed successfully!")
    print(f"Total chunks: {total_chunks}")
    print(f"ChromaDB count: {collection.count()}")
    print("--------------------------------")


if __name__ == "__main__":
    main()