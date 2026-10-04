import os

import chromadb
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# Connect to existing ChromaDB
chroma_client = chromadb.PersistentClient(
    path="../chroma_db"
)

collection = chroma_client.get_collection(
    name="sensrs_knowledge"
)


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")


def create_embedding(text):
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )

    return response.embeddings[0].values


question = "What is hyperspectral imaging?"

question_embedding = create_embedding(question)

results = collection.query(
    query_embeddings=[question_embedding],
    n_results=5
)

print("\nQUESTION:")
print(question)

print("\nRETRIEVED INFORMATION:")

for i, document in enumerate(results["documents"][0]):
    distance = results["distances"][0][i]

    print(f"\n--- Result {i+1} ---")
    print(f"Distance: {distance:.4f}")
    print(document)

print("\nSOURCES:")

for metadata in results["metadatas"][0]:
    print(metadata)