import os

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import errors
from pathlib import Path

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
        # 2. Create question embedding
        # -------------------------
        question_embedding = create_embedding(question)

        # -------------------------
        # 3. Search ChromaDB
        # -------------------------
        results = collection.query(
            query_embeddings=[question_embedding],
            n_results=8,
            include=[
                "documents",
                "metadatas",
                "distances"
            ]
        )

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

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

SEnSRS KNOWLEDGE BASE:

{context}

USER QUESTION:

{question}

Answer:
"""

        answer = None
        last_error = None

        for model_name in GENERATION_MODELS:
            try:
                chat_session = client.chats.create(model=model_name)
                res = chat_session.send_message(prompt)
                answer = res.text.strip()
                break
            except Exception as model_err:
                last_error = model_err
                continue

        if not answer:
            raise RuntimeError(f"All models failed. Last error: {last_error}")

        # -------------------------
        # 7. Filter sources
        # -------------------------
        sources = []

        for metadata, distance in zip(metadatas, distances):
            if distance <= 0.8:
                title = metadata.get("title")
                url = metadata.get("url")

                if title and url:
                    source = {
                        "title": title,
                        "url": url
                    }

                    if source not in sources:
                        sources.append(source)

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