import os

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
import time
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import errors
from urllib.parse import urlparse
from pathlib import Path
import json

load_dotenv()

# -------------------------
# Gemini
# -------------------------

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "gemini-embedding-2"
)

GENERATION_MODELS = [
    os.getenv("GENERATION_MODEL", "gemini-3.5-flash"),
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
]


# -------------------------
# ChromaDB
# -------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chroma_db"

chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)

collection = chroma_client.get_collection(
    name="sensrs_knowledge"
)


def get_display_title(title, url):
    generic_titles = {
        "",
        "sensrs - iit ropar",
        "sensrs"
    }

    title = (title or "").strip()

    if title.lower() not in generic_titles:
        return title

    path = urlparse(url or "").path.strip("/")

    if not path:
        return "SEnSRS Home"

    # Use the final URL path segment as a readable fallback.
    name = path.split("/")[-1]
    name = name.replace("-", " ").replace("_", " ")

    # Handle common website page names.
    known_titles = {
        "about": "About Us",
        "about us": "About Us",
        "visionandmission": "Vision and Mission",
        "projects": "Projects",
        "publications": "Publications",
        "internship": "Internships",
        "internships": "Internships",
        "phd programme": "PhD Programme",
        "opportunities": "Opportunities",
        "policy": "Policies",
        "consultancy services": "Consultancy Services",
        "contact": "Contact Us",
        "appointment": "Contact and Appointment",
        "photo gallery": "Photo Gallery",
        "video gallery": "Video Gallery",
        "press and news": "Press and News",
        "newsletter": "Newsletter",
        "research areas": "Research Areas",
        "consortium": "Consortium",
        "outreach": "Outreach",
        "people": "People",
        "events": "Events",
    }

    return known_titles.get(name.lower(), name.title())



# -------------------------
# FastAPI
# -------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str


# -------------------------
# Embedding
# -------------------------

def create_embedding(text):
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )

    return response.embeddings[0].values


# -------------------------
# Home
# -------------------------

@app.get("/")
def home():
    return {
        "message": "SEnSRS AI Backend is running!"
    }


# -------------------------
# RAG Chat
# -------------------------

@app.post("/chat")
def chat(request: ChatRequest):
    request_start = time.perf_counter()

    # -------------------------
    # 1. Validate question
    # -------------------------
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    try:
        # -------------------------
        # 2. Prepare search query & embedding
        # -------------------------
        search_question = question

        vacancy_keywords = [
            "vacancy", "vacancies", "job", "jobs",
            "recruitment", "hiring", "field investigator",
            "application deadline", "last date"
        ]

        if any(word in question.lower() for word in vacancy_keywords):
            search_question = (
                f"{question} Field Investigator recruitment "
                "vacancy announcement job opening application "
                "last date deadline eligibility current status"
            )

        embedding_start = time.perf_counter()
        question_embedding = create_embedding(search_question)
        embedding_time = time.perf_counter() - embedding_start

        # -------------------------
        # 3. Retrieve relevant documents from ChromaDB
        # -------------------------
        retrieval_start = time.perf_counter()
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=min(8, collection.count()),
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )
        retrieval_time = time.perf_counter() - retrieval_start

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        print(
            f"Embedding: {embedding_time:.2f}s | "
            f"Retrieval: {retrieval_time:.2f}s"
        )

        # -------------------------
        # 4. Check relevance
        # -------------------------
        best_distance = distances[0]
        print("Best retrieval distance:", best_distance)
        print("Retrieved document:", documents[0][:300])

        if best_distance > 0.8:
            return {
                "question": question,
                "answer": (
                    "I couldn't find this information "
                    "in the SEnSRS knowledge base."
                ),
                "sources": []
            }

        # -------------------------
        # 5. Build context
        # -------------------------
        context_parts = []

        for document, metadata, distance in zip(
            documents,
            metadatas,
            distances
        ):
            if distance <= 0.8:
                context_parts.append(
                    f"""
SOURCE:
Title: {metadata.get("title", "SEnSRS")}
URL: {metadata.get("url", "")}

CONTENT:
{document}
"""
                )

        context = "\n\n".join(context_parts)

        # -------------------------
        # 6. Generate answer
        # -------------------------

        prompt = f"""
You are the official SEnSRS AI Assistant for the SEnSRS website.

Answer the user's question using ONLY the information in the
SEnSRS knowledge base provided below.

IMPORTANT RULES:
1. If the knowledge base contains relevant information, answer the question.
2. Do not say that information is missing when relevant information is present.
3. Combine information from multiple relevant chunks when necessary.
4. Do not invent facts.
5. Keep the answer clear and concise.
6. Use the terminology used by SEnSRS.
7. Do not mention the retrieval process, embeddings, ChromaDB, or the knowledge base.
8. If the information genuinely cannot be found, say exactly:
"I couldn't find this information in the SEnSRS knowledge base."


VACANCY AND RECRUITMENT RULES:

- Answer vacancy questions using the retrieved SEnSRS information.
- Identify the specific post, announcement date, deadline,
  eligibility, and application link whenever available.
- Do not claim a vacancy is currently open just because it
  appears in an old announcement.
- If the application deadline has passed, state that clearly.
- If the current status cannot be confirmed, tell the user
  that the available information does not confirm whether
  applications are currently open.
- Never invent job openings, deadlines, eligibility, or links.
- If the retrieved information does not answer the question,
  say that you could not confirm the information from the
  SEnSRS knowledge base.


SEnSRS KNOWLEDGE BASE:

{context}

USER QUESTION:

{question}

Answer:
"""

        answer = None
        last_error = None
        generation_time = 0.0

        for model_name in GENERATION_MODELS:
            try:
                chat_session = client.chats.create(model=model_name)
                generation_start = time.perf_counter()
                res = chat_session.send_message(prompt)
                generation_time = time.perf_counter() - generation_start
                answer = res.text.strip()
                break
            except Exception as model_err:
                last_error = model_err
                continue

        print(
            f"Gemini generation: {generation_time:.2f}s | "
            f"Total so far: "
            f"{time.perf_counter() - request_start:.2f}s"
        )

        if not answer:
            raise RuntimeError(f"All models failed. Last error: {last_error}")

        # -------------------------
        # 7. Filter and format sources
        # -------------------------
        sources = []
        seen_urls = set()

        for metadata, distance in zip(metadatas, distances):
            if distance <= 0.8:
                url = (metadata.get("url") or "").strip()
                title = metadata.get("title") or ""

                if not url:
                    continue

                display_title = get_display_title(title, url)

                # Prevent duplicate source links even if several
                # chunks from the same page were retrieved.
                normalized_url = url.rstrip("/").lower()

                if normalized_url in seen_urls:
                    continue

                seen_urls.add(normalized_url)

                sources.append({
                    "title": display_title,
                    "url": url
                })


        # -------------------------
        # 8. Return response
        # -------------------------
        return {
            "question": question,
            "answer": answer,
            "sources": sources
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"AI service error: {str(e)}"
        )
