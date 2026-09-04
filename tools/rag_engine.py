# rag_engine.py
"""
Lightweight, zero-overhead Codebase RAG pipeline optimized for local edge/Raspberry Pi.
Provides syntax-aware tokenization, code chunking with line metadata, and BM25/TF-IDF retrieval.
"""
import math
import os
import re
from typing import List, Dict, Any, Optional


def tokenize_code(text: str) -> List[str]:
    """Tokenize code preserving symbols, splitting camelCase, snake_case, and identifiers."""
    # Split camelCase and snake_case
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    tokens = re.findall(r"[A-Za-z0-9_]+|[^\s\w]", s1.lower())
    return [t for t in tokens if len(t) > 1 or t.isalnum()]


class CodeChunk:
    def __init__(self, filepath: str, rel_path: str, start_line: int, end_line: int, content: str):
        self.filepath = filepath
        self.rel_path = rel_path
        self.start_line = start_line
        self.end_line = end_line
        self.content = content
        self.tokens = tokenize_code(content + " " + rel_path)


class BM25Index:
    """In-memory BM25 index with low RAM overhead."""
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: List[CodeChunk] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

    def build(self, chunks: List[CodeChunk]):
        self.chunks = chunks
        self.doc_lengths = [len(c.tokens) for c in chunks]
        self.avg_doc_len = sum(self.doc_lengths) / max(1, len(chunks))
        self.doc_freqs = {}

        for chunk in chunks:
            unique_tokens = set(chunk.tokens)
            for token in unique_tokens:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        total_docs = len(chunks)
        self.idf = {}
        for token, df in self.doc_freqs.items():
            # BM25 standard IDF with smoothing
            self.idf[token] = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        query_tokens = tokenize_code(query)
        if not query_tokens or not self.chunks:
            return []

        scores = [0.0] * len(self.chunks)

        for q_token in query_tokens:
            if q_token not in self.idf:
                continue
            token_idf = self.idf[q_token]

            for i, chunk in enumerate(self.chunks):
                # Count frequency of q_token in chunk
                tf = chunk.tokens.count(q_token)
                if tf == 0:
                    continue

                doc_len = self.doc_lengths[i]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[i] += token_idf * (numerator / denominator)

        # Sort by score descending
        scored_results = [
            (scores[i], self.chunks[i])
            for i in range(len(self.chunks))
            if scores[i] > 0
        ]
        scored_results.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, chunk in scored_results[:top_k]:
            results.append({
                "score": round(score, 4),
                "filepath": chunk.filepath,
                "rel_path": chunk.rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
            })
        return results


class CodeRAGEngine:
    """Manages workspace scanning, chunking, and code retrieval."""
    def __init__(self):
        self.index = BM25Index()
        self.indexed_path: Optional[str] = None
        self.total_files: int = 0
        self.total_chunks: int = 0
        self.allowed_extensions = {
            ".py", ".sh", ".bash", ".js", ".ts", ".html", ".css", ".json",
            ".md", ".yml", ".yaml", ".c", ".cpp", ".h", ".go", ".rs", ".txt", ".sql"
        }
        self.ignored_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "llm-env", "venv", ".dockerignore", "models"
        }

    def _chunk_file(self, abs_path: str, rel_path: str, chunk_size: int = 40, overlap: int = 10) -> List[CodeChunk]:
        chunks = []
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if not lines:
                return []

            total_lines = len(lines)
            if total_lines <= chunk_size:
                content = "".join(lines)
                chunks.append(CodeChunk(abs_path, rel_path, 1, total_lines, content))
                return chunks

            start = 0
            while start < total_lines:
                end = min(total_lines, start + chunk_size)
                chunk_lines = lines[start:end]
                content = "".join(chunk_lines)
                chunks.append(CodeChunk(abs_path, rel_path, start + 1, end, content))
                if end == total_lines:
                    break
                start += (chunk_size - overlap)
        except Exception:
            pass
        return chunks

    def index_directory(self, dir_path: str) -> Dict[str, Any]:
        """Index a directory and build BM25 code search index."""
        abs_dir = os.path.abspath(dir_path)
        if not os.path.exists(abs_dir) or not os.path.isdir(abs_dir):
            return {"success": False, "error": f"Invalid directory path: '{dir_path}'"}

        all_chunks = []
        indexed_files = 0

        for root, dirs, files in os.walk(abs_dir):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.allowed_extensions:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, abs_dir)
                    file_chunks = self._chunk_file(full_path, rel_path)
                    if file_chunks:
                        all_chunks.extend(file_chunks)
                        indexed_files += 1

        self.index.build(all_chunks)
        self.indexed_path = abs_dir
        self.total_files = indexed_files
        self.total_chunks = len(all_chunks)

        return {
            "success": True,
            "path": abs_dir,
            "files_indexed": indexed_files,
            "chunks_created": len(all_chunks),
        }

    def query(self, query_str: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Retrieve relevant code snippets for query."""
        if not self.indexed_path:
            return []
        return self.index.search(query_str, top_k=top_k)

    def format_context_for_prompt(self, query_str: str, top_k: int = 3) -> str:
        """Format retrieved code chunks directly as prompt context."""
        results = self.query(query_str, top_k=top_k)
        if not results:
            return ""

        context_blocks = ["### Relevant Codebase Context (from RAG):"]
        for r in results:
            header = f"File: {r['rel_path']} (Lines {r['start_line']}-{r['end_line']}) [Relevance: {r['score']}]:"
            context_blocks.append(f"```\n{header}\n{r['content'].strip()}\n```")
        return "\n\n".join(context_blocks)

    def get_status(self) -> Dict[str, Any]:
        return {
            "indexed": self.indexed_path is not None,
            "path": self.indexed_path or "None",
            "files": self.total_files,
            "chunks": self.total_chunks,
        }


# Global singleton instance for easy import across modules
rag_engine = CodeRAGEngine()
