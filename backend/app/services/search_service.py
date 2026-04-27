"""Search and replace service for document text content.

Provides text search (with regex support), single replacement,
and batch replacement functionality via the SearchService class.
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, FileType, ReplacementLog, ReplacementType
from app.services.hwp_service import HwpService


class SearchServiceError(Exception):
    """Base exception for search service errors."""


class SearchService:
    """Service for text search and replace operations."""

    def __init__(self) -> None:
        self._hwp_service = HwpService()

    def search(
        self,
        text: str,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        context_chars: int = 30,
    ) -> list[dict]:
        """Search for text occurrences with line/column information.

        Returns:
            List of {
                "index": int,      # 0-based match index
                "line": int,       # 1-based line number
                "column": int,     # 1-based column number
                "match": str,      # matched text
                "context": str,    # surrounding context
                "position": int,   # absolute character position
            }
        """
        if not text or not query:
            return []

        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            pattern = re.compile(query if use_regex else re.escape(query), flags)
        except re.error as e:
            raise SearchServiceError(f"잘못된 정규식 패턴입니다: {e}")

        # Pre-compute line starts for O(1) line/column lookup
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)

        matches = []
        for idx, m in enumerate(pattern.finditer(text)):
            pos = m.start()

            # Binary search for line number
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= pos:
                    lo = mid
                else:
                    hi = mid - 1
            line = lo + 1  # 1-based
            column = pos - line_starts[lo] + 1  # 1-based

            ctx_start = max(0, pos - context_chars)
            ctx_end = min(len(text), m.end() + context_chars)

            matches.append({
                "index": idx,
                "line": line,
                "column": column,
                "match": m.group(),
                "context": text[ctx_start:ctx_end],
                "position": pos,
            })

        return matches

    def replace_single(
        self,
        text: str,
        query: str,
        replacement: str,
        occurrence: int = 0,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> tuple[str, bool]:
        """Replace a single occurrence of search text.

        Args:
            occurrence: 0-based index of which match to replace.

        Returns:
            (new_text, was_replaced)
        """
        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            pattern = re.compile(query if use_regex else re.escape(query), flags)
        except re.error as e:
            raise SearchServiceError(f"잘못된 정규식 패턴입니다: {e}")

        matches = list(pattern.finditer(text))
        if occurrence >= len(matches):
            return text, False

        m = matches[occurrence]
        if use_regex:
            replace_str = m.expand(replacement)
        else:
            replace_str = replacement

        new_text = text[: m.start()] + replace_str + text[m.end() :]
        return new_text, True

    def replace_all(
        self,
        text: str,
        query: str,
        replacement: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> tuple[str, int]:
        """Replace all occurrences of search text.

        Returns:
            (new_text, replacement_count)
        """
        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            pattern = re.compile(query if use_regex else re.escape(query), flags)
        except re.error as e:
            raise SearchServiceError(f"잘못된 정규식 패턴입니다: {e}")

        new_text, count = pattern.subn(replacement, text)
        return new_text, count

    async def search_in_document(
        self,
        document: Document,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> list[dict]:
        """Search text in a document (file or stored content)."""
        if document.file_type == FileType.HWPX:
            try:
                content = await self._hwp_service.get_text_content(document.file_path)
            except Exception:
                content = document.content_text or ""
        else:
            content = document.content_text or ""

        return self.search(content, query, case_sensitive, use_regex)

    async def replace_text_in_document(
        self,
        db: AsyncSession,
        document: Document,
        search: str,
        replace_with: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> tuple[int, int]:
        """Search and replace text in a document's HWPX file.

        Returns (replaced_count, new_version_number).
        """
        if document.file_type != FileType.HWPX:
            raise SearchServiceError("현재 HWPX 파일만 수정을 지원합니다.")

        new_path, count = self._hwp_service.replace_text(
            document.file_path, search, replace_with, case_sensitive, use_regex
        )

        if count > 0:
            log = ReplacementLog(
                document_id=document.id,
                field_name="text",
                old_value=search,
                new_value=replace_with,
                replacement_type=ReplacementType.SEARCH,
            )
            db.add(log)

            new_content = await self._hwp_service.get_text_content(new_path)
            summary = f"검색/치환: '{search}' -> '{replace_with}' ({count}건)"

            from app.services.document_service import create_version

            version = await create_version(
                db, document, new_path, new_content, summary
            )
            return count, version.version_number

        return 0, 0


# ── Module-level convenience functions ──

_service = SearchService()

search_text = _service.search
replace_single = _service.replace_single
replace_all = _service.replace_all


async def search_in_document(
    document: Document,
    query: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
) -> list[dict]:
    return await _service.search_in_document(
        document, query, case_sensitive, use_regex
    )


async def replace_text_in_document(
    db: AsyncSession,
    document: Document,
    search: str,
    replace_with: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
) -> tuple[int, int]:
    return await _service.replace_text_in_document(
        db, document, search, replace_with, case_sensitive, use_regex
    )
