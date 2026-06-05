"""Diff and version comparison service.

Generates text and table diffs between document versions and handles
revert (rollback) operations via the DiffService class.
"""

import difflib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentVersion


class DiffServiceError(Exception):
    """Base exception for diff service errors."""


class DiffService:
    """Service for generating diffs and managing version comparisons."""

    def generate_diff(self, original: str, modified: str) -> dict:
        """Generate a comprehensive diff between two texts.

        Returns: {
            "changes": [{
                "type": "add" | "delete" | "modify",
                "line": int,
                "old_value": str,
                "new_value": str,
            }],
            "summary": {
                "added": int,
                "deleted": int,
                "modified": int,
            },
            "unified_diff": str,
        }
        """
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()

        matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)

        changes: list[dict] = []
        added = 0
        deleted = 0
        modified_count = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            elif tag == "insert":
                for j in range(j1, j2):
                    changes.append({
                        "type": "add",
                        "line": j + 1,
                        "old_value": "",
                        "new_value": modified_lines[j],
                    })
                    added += 1
            elif tag == "delete":
                for i in range(i1, i2):
                    changes.append({
                        "type": "delete",
                        "line": i + 1,
                        "old_value": original_lines[i],
                        "new_value": "",
                    })
                    deleted += 1
            elif tag == "replace":
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    old_val = original_lines[i1 + k] if i1 + k < i2 else ""
                    new_val = modified_lines[j1 + k] if j1 + k < j2 else ""
                    line_num = (i1 + k + 1) if i1 + k < i2 else (j1 + k + 1)
                    changes.append({
                        "type": "modify",
                        "line": line_num,
                        "old_value": old_val,
                        "new_value": new_val,
                    })
                    modified_count += 1

        # Generate unified diff string
        unified = "".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="원본",
            tofile="수정본",
            n=3,
        ))

        return {
            "changes": changes,
            "summary": {
                "added": added,
                "deleted": deleted,
                "modified": modified_count,
            },
            "unified_diff": unified,
        }

    def generate_table_diff(
        self,
        original_tables: list[dict],
        modified_tables: list[dict],
    ) -> list[dict]:
        """Generate cell-level diff between two sets of tables.

        Args:
            original_tables: List from HwpService.extract_tables() (original).
            modified_tables: List from HwpService.extract_tables() (modified).

        Returns:
            List of {
                "table_index": int,
                "changes": [{
                    "row": int,
                    "col": int,
                    "old_value": str,
                    "new_value": str,
                }],
            }
        """
        table_diffs: list[dict] = []

        # Compare tables by index
        max_tables = max(len(original_tables), len(modified_tables))
        for t_idx in range(max_tables):
            orig = original_tables[t_idx] if t_idx < len(original_tables) else None
            mod = modified_tables[t_idx] if t_idx < len(modified_tables) else None

            if orig is None and mod is not None:
                # Entire table added
                changes = []
                for row_idx, row in enumerate(mod.get("rows", [])):
                    for col_idx, cell in enumerate(row):
                        if cell:
                            changes.append({
                                "row": row_idx,
                                "col": col_idx,
                                "old_value": "",
                                "new_value": cell,
                            })
                if changes:
                    table_diffs.append({"table_index": t_idx, "changes": changes})
                continue

            if mod is None and orig is not None:
                # Entire table deleted
                changes = []
                for row_idx, row in enumerate(orig.get("rows", [])):
                    for col_idx, cell in enumerate(row):
                        if cell:
                            changes.append({
                                "row": row_idx,
                                "col": col_idx,
                                "old_value": cell,
                                "new_value": "",
                            })
                if changes:
                    table_diffs.append({"table_index": t_idx, "changes": changes})
                continue

            # Both exist - compare cell by cell
            orig_rows = orig.get("rows", []) if orig else []
            mod_rows = mod.get("rows", []) if mod else []
            max_rows = max(len(orig_rows), len(mod_rows))

            changes = []
            for row_idx in range(max_rows):
                orig_row = orig_rows[row_idx] if row_idx < len(orig_rows) else []
                mod_row = mod_rows[row_idx] if row_idx < len(mod_rows) else []
                max_cols = max(len(orig_row), len(mod_row))

                for col_idx in range(max_cols):
                    old_val = orig_row[col_idx] if col_idx < len(orig_row) else ""
                    new_val = mod_row[col_idx] if col_idx < len(mod_row) else ""
                    if old_val != new_val:
                        changes.append({
                            "row": row_idx,
                            "col": col_idx,
                            "old_value": old_val,
                            "new_value": new_val,
                        })

            if changes:
                table_diffs.append({"table_index": t_idx, "changes": changes})

        return table_diffs

    def generate_inline_diff(self, original: str, modified: str) -> list[dict]:
        """Generate an inline (side-by-side) diff representation.

        Returns list of {
            "type": "equal" | "insert" | "delete" | "replace",
            "original_line": int | None,
            "modified_line": int | None,
            "original_text": str,
            "modified_text": str,
        }
        """
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()

        matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)
        result = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    result.append({
                        "type": "equal",
                        "original_line": i + 1,
                        "modified_line": j + 1,
                        "original_text": original_lines[i],
                        "modified_text": modified_lines[j],
                    })
            elif tag == "delete":
                for i in range(i1, i2):
                    result.append({
                        "type": "delete",
                        "original_line": i + 1,
                        "modified_line": None,
                        "original_text": original_lines[i],
                        "modified_text": "",
                    })
            elif tag == "insert":
                for j in range(j1, j2):
                    result.append({
                        "type": "insert",
                        "original_line": None,
                        "modified_line": j + 1,
                        "original_text": "",
                        "modified_text": modified_lines[j],
                    })
            elif tag == "replace":
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    orig = original_lines[i1 + k] if i1 + k < i2 else ""
                    mod = modified_lines[j1 + k] if j1 + k < j2 else ""
                    result.append({
                        "type": "replace",
                        "original_line": (i1 + k + 1) if i1 + k < i2 else None,
                        "modified_line": (j1 + k + 1) if j1 + k < j2 else None,
                        "original_text": orig,
                        "modified_text": mod,
                    })

        return result


# ── Module-level functions ──

_service = DiffService()


async def get_version_text(
    db: AsyncSession,
    document_id: int,
    version_number: int,
) -> str | None:
    """Get the content text of a specific version."""
    stmt = (
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
    )
    result = await db.execute(stmt)
    version = result.scalar_one_or_none()
    if not version:
        raise DiffServiceError(f"버전 {version_number}을(를) 찾을 수 없습니다.")
    return version.content_text


async def get_diff(
    db: AsyncSession,
    document: Document,
    version_number: int | None = None,
) -> dict:
    """Get diff between original (v1) and a specific version."""
    try:
        original_text = await get_version_text(db, document.id, 1) or ""
    except DiffServiceError:
        original_text = ""

    if version_number:
        modified_text = await get_version_text(db, document.id, version_number) or ""
        ver_num = version_number
    else:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        latest = result.scalar_one_or_none()
        modified_text = (latest.content_text if latest else document.content_text) or ""
        ver_num = latest.version_number if latest else 1

    diff_data = _service.generate_diff(original_text, modified_text)

    return {
        "document_id": document.id,
        "original_text": original_text,
        "modified_text": modified_text,
        "version_number": ver_num,
        "unified_diff": diff_data["unified_diff"],
        "stats": diff_data["summary"],
    }


async def revert_to_version(
    db: AsyncSession,
    document: Document,
    version_number: int,
) -> Document:
    """Revert document to a specific version."""
    stmt = (
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == version_number,
        )
    )
    result = await db.execute(stmt)
    target_version = result.scalar_one_or_none()
    if not target_version:
        raise DiffServiceError(f"버전 {version_number}을(를) 찾을 수 없습니다.")

    summary = f"버전 {version_number}으로 되돌림"

    from app.services.document_service import create_version

    # file_data가 있으면 DB 바이너리 사용, 없으면 빈 bytes
    revert_data = target_version.file_data or b""
    await create_version(
        db, document, revert_data, target_version.content_text, summary
    )

    await db.refresh(document)
    return document
