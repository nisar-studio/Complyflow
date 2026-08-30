"""
ComplyFlow — Intelligent Document Chunking & Context Assembly Service

Provides structured, section- and page-aware chunking for compliance documents.
Eliminates naive text slicing (e.g. [:8000]) and preserves source context,
exact excerpts, section headers, and page numbers for audit citations.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A structured chunk of a compliance document with full provenance metadata."""
    chunk_id: str = Field(default_factory=lambda: f"chk_{uuid.uuid4().hex[:8]}")
    document_id: str = ""
    document_name: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int = 0
    text: str
    character_count: int = 0
    token_estimate: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.character_count:
            self.character_count = len(self.text)
        if not self.token_estimate:
            # Conservative standard rule of thumb: ~4 characters per token
            self.token_estimate = max(1, len(self.text) // 4)


class ChunkedDocument(BaseModel):
    """Complete representation of a document with its structured chunks and parsing health."""
    document_id: str
    document_name: str
    total_pages: int = 1
    total_characters: int = 0
    total_chunks: int = 0
    status: str = "OK"  # "OK" | "OCR_REQUIRED" | "EMPTY"
    diagnostics: str = ""
    chunks: List[DocumentChunk] = Field(default_factory=list)
    raw_text: str = ""


class ChunkingService:
    """
    Intelligent chunking engine.
    Splits text along section headers, paragraph boundaries, and PDF pages.
    """

    # Section / Header detection patterns
    SECTION_HEADER_PATTERN = re.compile(
        r"^(?:(?:SECTION|ARTICLE|PART|CHAPTER|CLAUSE)\s+[\dA-Z.-]+|"
        r"(?:REQ|REQ-|\d+\.\d+|\d+\.)\s+[A-Z0-9].*|"
        r"#{1,4}\s+.*|"
        r"[A-Z0-9\s,._-]{4,60}:|"
        r"[A-Z\s]{4,40}$)",
        re.MULTILINE,
    )

    def __init__(self, target_chunk_size: int = 1200, chunk_overlap: int = 150):
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_plain_text(
        self,
        text: str,
        document_name: str,
        document_id: str = "",
        page_number: Optional[int] = None,
    ) -> List[DocumentChunk]:
        """
        Chunk a text block using section header and paragraph boundaries.
        Preserves natural sentences and avoids mid-sentence cuts.
        """
        clean_text = text.strip()
        if not clean_text:
            return []

        doc_id = document_id or document_name.replace(" ", "_")
        paragraphs = re.split(r"\n\s*\n", clean_text)
        
        chunks: List[DocumentChunk] = []
        current_chunk_paragraphs: List[str] = []
        current_length = 0
        current_section: Optional[str] = None
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if this paragraph starts with a section header
            lines = para.splitlines()
            first_line = lines[0].strip() if lines else ""
            is_new_section = bool(self.SECTION_HEADER_PATTERN.match(first_line))
            
            # If this is a new section and we already have accumulated meaningful content (>120 chars),
            # flush current chunk to keep section boundaries aligned
            if is_new_section and current_length > 120 and current_chunk_paragraphs:
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                chunks.append(
                    DocumentChunk(
                        document_id=doc_id,
                        document_name=document_name,
                        page_number=page_number,
                        section=current_section,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                    )
                )
                chunk_idx += 1
                current_chunk_paragraphs = []
                current_length = 0

            if is_new_section:
                current_section = first_line[:80]

            para_len = len(para)

            # If adding this paragraph exceeds target size and we already have content, yield chunk
            if current_length + para_len > self.target_chunk_size and current_chunk_paragraphs:
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                chunks.append(
                    DocumentChunk(
                        document_id=doc_id,
                        document_name=document_name,
                        page_number=page_number,
                        section=current_section,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                    )
                )
                chunk_idx += 1
                current_chunk_paragraphs = []
                current_length = 0

            # If a single paragraph is larger than target_chunk_size, split by sentences
            if para_len > self.target_chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                sub_chunk_sentences: List[str] = []
                sub_length = 0

                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if sub_length + len(sent) > self.target_chunk_size and sub_chunk_sentences:
                        sub_text = " ".join(sub_chunk_sentences)
                        chunks.append(
                            DocumentChunk(
                                document_id=doc_id,
                                document_name=document_name,
                                page_number=page_number,
                                section=current_section,
                                chunk_index=chunk_idx,
                                text=sub_text,
                            )
                        )
                        chunk_idx += 1
                        sub_chunk_sentences = []
                        sub_length = 0
                    sub_chunk_sentences.append(sent)
                    sub_length += len(sent) + 1

                if sub_chunk_sentences:
                    current_chunk_paragraphs.append(" ".join(sub_chunk_sentences))
                    current_length += sub_length
            else:
                current_chunk_paragraphs.append(para)
                current_length += para_len + 2  # account for \n\n

        if current_chunk_paragraphs:
            chunk_text = "\n\n".join(current_chunk_paragraphs)
            chunks.append(
                DocumentChunk(
                    document_id=doc_id,
                    document_name=document_name,
                    page_number=page_number,
                    section=current_section,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                )
            )

        return chunks

    def chunk_pdf_pages(
        self,
        pages_text: List[str],
        document_name: str,
        document_id: str = "",
    ) -> ChunkedDocument:
        """
        Chunk a multi-page PDF document, preserving page numbers for each chunk.
        Detects scanned/empty PDFs and flags OCR_REQUIRED.
        """
        doc_id = document_id or document_name.replace(" ", "_")
        total_pages = max(1, len(pages_text))
        all_chunks: List[DocumentChunk] = []
        full_text_parts: List[str] = []
        non_empty_pages = 0

        for page_idx, page_str in enumerate(pages_text, start=1):
            clean_page = page_str.strip()
            if clean_page:
                non_empty_pages += 1
                full_text_parts.append(f"[Page {page_idx}]\n{clean_page}")
                page_chunks = self.chunk_plain_text(
                    text=clean_page,
                    document_name=document_name,
                    document_id=doc_id,
                    page_number=page_idx,
                )
                all_chunks.extend(page_chunks)

        full_raw_text = "\n\n".join(full_text_parts).strip()
        total_chars = len(full_raw_text)

        # Scanned PDF Detection
        if total_pages > 0 and non_empty_pages == 0:
            return ChunkedDocument(
                document_id=doc_id,
                document_name=document_name,
                total_pages=total_pages,
                total_characters=0,
                total_chunks=0,
                status="OCR_REQUIRED",
                diagnostics=f"OCR_REQUIRED: PDF has {total_pages} page(s) but no extractable text was found. Document may be scanned or image-only.",
                chunks=[],
                raw_text="",
            )

        return ChunkedDocument(
            document_id=doc_id,
            document_name=document_name,
            total_pages=total_pages,
            total_characters=total_chars,
            total_chunks=len(all_chunks),
            status="OK",
            diagnostics=f"Successfully extracted {len(all_chunks)} chunks across {total_pages} page(s).",
            chunks=all_chunks,
            raw_text=full_raw_text,
        )

    def assemble_context(
        self,
        chunks: List[DocumentChunk],
        max_tokens: int = 30000,
        header_prefix: str = "--- DOCUMENT EVIDENCE CHUNKS ---",
    ) -> str:
        """
        Assemble chunks into a token-safe prompt context.
        Injects rich provenance headers: [Document: <name> | Page: <p> | Section: <s>]
        Respects max_tokens budget without character-level cutting.
        """
        if not chunks:
            return ""

        assembled_lines: List[str] = [header_prefix]
        current_token_count = len(header_prefix) // 4

        for chunk in chunks:
            meta_header = f"\n[SOURCE: {chunk.document_name}"
            if chunk.page_number is not None:
                meta_header += f" | Page: {chunk.page_number}"
            if chunk.section:
                meta_header += f" | Section: {chunk.section}"
            meta_header += f" | Chunk: {chunk.chunk_index + 1}]\n"

            chunk_content = f"{meta_header}{chunk.text}\n"
            estimated_tokens = len(chunk_content) // 4

            if current_token_count + estimated_tokens > max_tokens:
                assembled_lines.append("\n[Context limit reached: remaining chunks truncated safely at chunk boundary]")
                break

            assembled_lines.append(chunk_content)
            current_token_count += estimated_tokens

        return "".join(assembled_lines)


# Global singleton instance
_chunking_service_instance: Optional[ChunkingService] = None


def get_chunking_service() -> ChunkingService:
    global _chunking_service_instance
    if _chunking_service_instance is None:
        _chunking_service_instance = ChunkingService()
    return _chunking_service_instance
