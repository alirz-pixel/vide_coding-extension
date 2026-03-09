import chromadb
import ollama

from pathlib import Path
from sentence_transformers import SentenceTransformer

from prompts.builder import PromptBuilder

BASE_PATH = Path(__file__).parent

model = SentenceTransformer("BAAI/bge-m3")  # VRAM: ~ 3GB
client = chromadb.PersistentClient(path=BASE_PATH / "chroma_db")
builder = PromptBuilder("keyword.yaml")

NOISE_KEYWORDS = {
    "cpp": ["int", "main", "return", "using", "namespace", "std", "cin", "cout", "endl", "include"],
    "python": ["def", "return", "if", "else", "for", "while", "import", "print", "self", "class"],
    "javascript": ["const", "let", "var", "function", "return", "if", "else", "for", "console"],
}

ALGORITHM_KEYWORDS = [
    "sort", "search", "tree", "graph", "queue", "stack", "heap",
    "dynamic", "greedy", "recursive", "hash", "linked", "binary",
    "bubble", "merge", "quick", "insert", "delete", "traverse",
    "vector", "array", "list", "map", "set", "priority"
]

def extract_keywords_llm(code: str) -> str:
    response = ollama.chat(
        model="qwen2.5:1.5b",
        messages=[
            {"role": "system", "content": builder.build_system()},
            {"role": "user", "content": code}
        ]
    )
    keywords = response["message"]["content"].strip()
    keywords = keywords.replace(",", " ") # 키워드는 공백으로 구분되도록 전환
    return keywords


def retrieve(code: str, language: str, top_k: int = 3) -> str:
    query = extract_keywords_llm(code)

    if not query:
        query = code[:200]  # 키워드 없으면 코드 앞부분 사용

    embedding = model.encode([query]).tolist()
    context = ""

    # 언어별 문서 + 알고리즘 문서 둘 다 검색
    collections_to_search = ["algorithm"]

    for col_name in collections_to_search:
        try:
            collection = client.get_collection(name=col_name)
        except Exception as e:
            print(e)
            continue

        results = collection.query(
            query_embeddings=embedding,
            n_results=top_k
        )

        docs = results["documents"][0]
        urls = [m["url"] for m in results["metadatas"][0]]

        for i, (doc, url) in enumerate(zip(docs, urls)):
            context += f"\n[참고 문서 - {col_name}] 출처: {url}\n{doc[:300]}\n"

    return context


if __name__ == '__main__':
    ret = retrieve("""
#include <iostream>
using namespace std;

struct Node {
    int data;
    Node* left;
    Node* right;
    Node(int val) : data(val), left(nullptr), right(nullptr) {}
};

Node* insert(Node* root, int val) {
    if (!root) return new Node(val);
    if (val < root->data)
        root->left = insert(root->left, val);
    else
        root->right = insert(root->right, val);
    return root;
}

bool search(Node* root, int val) {
    if (!root) return false;
    if (root->data == val) return true;
    if (val < root->data)
        return search(root->left, val);
    return search(root->right, val);
}

int main() {
    Node* root = nullptr;
    root = insert(root, 5);
    root = insert(root, 3);
    root = insert(root, 7);
    cout << search(root, 3) << endl;
    return 0;
}
""", "cpp")

    print(ret)