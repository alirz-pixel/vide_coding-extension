import requests
import chromadb
import hashlib
import re
import os

from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from concurrent.futures import ThreadPoolExecutor, as_completed


# 크롤링할 공식 문서 URL 목록
DOCS = {
    "algorithm": [
        # 정렬
        "https://en.wikipedia.org/wiki/Sorting_algorithm",
        "https://en.wikipedia.org/wiki/Merge_sort",
        "https://en.wikipedia.org/wiki/Quick_sort",
        "https://en.wikipedia.org/wiki/Heap_sort",
        "https://en.wikipedia.org/wiki/Bubble_sort",

        # 탐색
        "https://en.wikipedia.org/wiki/Binary_search_algorithm",
        "https://en.wikipedia.org/wiki/Breadth-first_search",
        "https://en.wikipedia.org/wiki/Depth-first_search",
        "https://en.wikipedia.org/wiki/A*_search_algorithm",

        # 그래프
        "https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm",
        "https://en.wikipedia.org/wiki/Bellman%E2%80%93Ford_algorithm",
        "https://en.wikipedia.org/wiki/Floyd%E2%80%93Warshall_algorithm",
        "https://en.wikipedia.org/wiki/Kruskal%27s_algorithm",

        # 동적 프로그래밍
        "https://en.wikipedia.org/wiki/Dynamic_programming",
        "https://en.wikipedia.org/wiki/Longest_common_subsequence",
        "https://en.wikipedia.org/wiki/Knapsack_problem",

        # 자료구조
        "https://en.wikipedia.org/wiki/Linked_list",
        "https://en.wikipedia.org/wiki/Stack_(abstract_data_type)",
        "https://en.wikipedia.org/wiki/Queue_(abstract_data_type)",
        "https://en.wikipedia.org/wiki/Binary_tree",
        "https://en.wikipedia.org/wiki/Binary_search_tree",
        "https://en.wikipedia.org/wiki/AVL_tree",
        "https://en.wikipedia.org/wiki/Hash_table",
        "https://en.wikipedia.org/wiki/Heap_(data_structure)",
        "https://en.wikipedia.org/wiki/Graph_(abstract_data_type)",
    ],
    "cpp": [
        "https://en.cppreference.com/w/cpp/container/vector",
        "https://en.cppreference.com/w/cpp/memory",
        "https://en.cppreference.com/w/cpp/algorithm",
    ]
}

MAX_WORKER = max(5, os.cpu_count())

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

model = SentenceTransformer("BAAI/bge-m3")  # VRAM: ~ 3GB
client = chromadb.PersistentClient(path="./chroma_db")

def chunk_text(text: str, max_words: int = 500) -> list[str]:
    """
    문단 단위로 추출된 크롤링 결과를 vector DB에 담도록 함.
    문단의 글자수가 너무 긴 경우엔 문장 단위로 잘라서 500글자 제한을 둠
    (의미가 퇴색됨을 방지)
    """

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(para.split()) > max_words:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                if len((current_chunk + " " + sentence).split()) > max_words and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    current_chunk += " " + sentence
        else:
            if len((current_chunk + " " + para).split()) > max_words and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk += "\n\n" + para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def parse_table(table_tag) -> str:
    rows = table_tag.find_all("tr")
    if not rows:
        return ""

    # 첫 번째 행을 헤더로
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

    result = []
    for row in rows[1:]:
        cols = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
        if not any(cols):
            continue
        # 헤더: 값 형태로 조립
        paired = [f"{h}: {v}" for h, v in zip(headers, cols) if h and v]
        result.append(" | ".join(paired))

    return "\n".join(result)


def crawl(url: str) -> str:
    res = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    # 불필요한 태그 제거
    for tag in soup(["script", "nav", "style", "header", "footer"]):
        tag.decompose()

    # head 영역 제거
    body = soup.find("body")
    if not body:
        return ""

    for tag in body.find_all(class_=["toc", "sidebar", "navbox", "editsection", "t-navbar"]):
        tag.decompose()

    sections = []
    current_section = []

    for tag in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        if tag.name == "table":
            text = parse_table(tag)
        else:
            text = tag.get_text(strip=True)

        if not text:
            continue

        # 헤더 및 tr 단위로의 분할
        if tag.name in ["h1", "h2", "h3", "h4"]:
            if current_section:
                sections.append("\n".join(current_section))
            current_section = [text]
        else:
            current_section.append(text)
    if current_section:
        sections.append("\n".join(current_section))
    return "\n\n".join(sections)


def ingest():
    for language, urls in DOCS.items():
        collection = client.get_or_create_collection(name=language)
        print(f"\n[{language}] 크롤링 시작 ({len(urls)}개 URL)")

        # 1. 크롤링을 멀티 스레딩으로 진행
        print(f"  멀티스레딩 workers: {MAX_WORKER}")

        crawl_results = {}  # {url: text}
        with ThreadPoolExecutor(max_workers=MAX_WORKER) as executor:
            futures = {executor.submit(crawl, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                text = future.result()
                if text:
                    crawl_results[url] = text
                    print(f"  크롤링 완료: {url}")
                else:
                    print(f"  빈 내용: {url}")

        # 2. 청크 분할
        print(f"\n[{language}] 청크 분할 중...")
        all_chunks = []   # [(url, chunk), ...]
        for url, text in crawl_results.items():
            chunks = chunk_text(text)
            for chunk in chunks:
                all_chunks.append((url, chunk))

        if not all_chunks:
            print(f"  저장할 청크 없음")
            continue

        print(f"  총 {len(all_chunks)}개 청크")

        # 3. 임베딩 배치 처리
        print(f"[{language}] 임베딩 생성 중...")
        texts_only = [chunk for _, chunk in all_chunks]
        embeddings = model.encode(
            texts_only,
            batch_size=32,  # 32개씩 묶어서 GPU 효율 극대화
            show_progress_bar=True
        ).tolist()

        # 4. Vector DB에 저장
        print(f"[{language}] 벡터 DB 저장 중...")
        ids = [hashlib.md5(f"{url}_{i}".encode()).hexdigest()
               for i, (url, _) in enumerate(all_chunks)]
        metadatas = [{"url": url, "language": language}
                     for url, _ in all_chunks]


        batch_size = 500
        for i in range(0, len(all_chunks), batch_size):
            collection.upsert(
                ids=ids[i:i+batch_size],
                documents=texts_only[i:i+batch_size],
                embeddings=embeddings[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size]
            )
        print(f"  {len(all_chunks)}개 청크 저장 완료")

    print("\n 전체 문서 수집 완료")


def test():
    collections = client.list_collections()
    print("컬렉션 목록:", [c.name for c in collections])

    collection = client.get_collection("algorithm")
    print("총 청크 수:", collection.count())

    result = collection.get(limit=5)
    for i, (doc, meta) in enumerate(zip(result["documents"], result["metadatas"])):
        print(f"\n--- 청크 {i + 1} ---")
        print(f"출처: {meta['url']}")
        print(f"내용: {doc[:200]}...")



if __name__ == "__main__":
    ingest()
    print("\n 전체 문서 수집 완료")
    test()
