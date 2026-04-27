"""맞춤법 검사 서비스.

규칙 기반 맞춤법 검사 및 법률 용어 오타 검출을 제공합니다.
외부 API 의존 없이 자체 규칙과 용어 사전으로 동작합니다.
"""

import re


class SpellCheckServiceError(Exception):
    """Base exception for spellcheck service errors."""


# ── 자주 틀리는 맞춤법 규칙 (도시계획/법률 문서 특화) ──

COMMON_MISSPELLINGS: dict[str, str] = {
    # 띄어쓰기 오류
    "할수있": "할 수 있",
    "할수없": "할 수 없",
    "할것임": "할 것임",
    "할것이": "할 것이",
    "있슴": "있음",
    "없슴": "없음",
    "됬": "됐",
    "됫": "됐",
    "안됨": "안 됨",
    "못함": "못 함",
    "할께": "할게",
    "할꺼": "할 거",
    "할껀": "할 건",
    "있읍니다": "있습니다",
    "없읍니다": "없습니다",
    "하겟습니다": "하겠습니다",
    "되겠읍니다": "되겠습니다",
    # 조사 오류
    "의거해": "의거하여",
    "근거해": "근거하여",
    # 도시계획 관련
    "도시계획시설": "도시·군계획시설",
    "지구단위계획구역": "지구단위계획 구역",
}

# ── 법률 용어 사전 (올바른 표기) ──

LEGAL_TERMS: dict[str, list[str]] = {
    # 올바른 표기: [흔한 오타들]
    "국토의 계획 및 이용에 관한 법률": [
        "국토의계획및이용에관한법률",
        "국토계획및이용에관한법률",
        "국토의 계획및 이용에 관한 법률",
        "국토계획이용법",
    ],
    "도시 및 주거환경정비법": [
        "도시및주거환경정비법",
        "도시주거환경정비법",
        "도시 및 주거환경 정비법",
    ],
    "건축법": ["건축법률"],
    "도시개발법": ["도시개발 법", "도시 개발 법"],
    "택지개발촉진법": ["택지개발 촉진법"],
    "도시공원 및 녹지 등에 관한 법률": [
        "도시공원및녹지등에관한법률",
        "도시공원녹지법",
    ],
    "환경영향평가법": ["환경영향 평가법", "환경 영향평가법"],
    "공익사업을 위한 토지 등의 취득 및 보상에 관한 법률": [
        "공익사업을위한토지등의취득및보상에관한법률",
        "토지보상법",
    ],
    "지방자치법": ["지방자치 법"],
    "행정절차법": ["행정절차 법"],
    "개발이익 환수에 관한 법률": [
        "개발이익환수에관한법률",
        "개발이익환수법",
    ],
}

# ── 숫자/날짜 표기 규칙 ──

DATE_PATTERNS = [
    # YYYY.MM.DD -> YYYY년 MM월 DD일 (문서 내 일관성)
    (re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?"), None),  # detect only
]

NUMBER_UNIT_PATTERNS = [
    # 숫자+단위 띄어쓰기
    (re.compile(r"(\d)(㎡)"), r"\1 \2"),
    (re.compile(r"(\d)(㎢)"), r"\1 \2"),
    (re.compile(r"(\d)(km)"), r"\1 \2"),
]


class SpellCheckService:
    """맞춤법 검사 서비스."""

    async def check_text(self, text: str) -> list[dict]:
        """텍스트 맞춤법 검사.

        Returns:
            List of {
                "original": str,
                "corrected": str,
                "position": int,
                "type": "spelling" | "spacing" | "grammar",
            }
        """
        if not text:
            return []

        errors: list[dict] = []

        # 1. 자주 틀리는 맞춤법 검사
        errors.extend(self._check_common_misspellings(text))

        # 2. 띄어쓰기 규칙 검사
        errors.extend(self._check_spacing_rules(text))

        # 3. 숫자/단위 표기 검사
        errors.extend(self._check_number_units(text))

        # Sort by position and deduplicate
        errors.sort(key=lambda e: e["position"])
        return self._deduplicate(errors)

    async def check_legal_terms(self, text: str) -> list[dict]:
        """법률 용어 오타 검출.

        Returns:
            List of {
                "found": str,
                "suggested": str,
                "position": int,
            }
        """
        if not text:
            return []

        findings: list[dict] = []

        for correct_term, wrong_variants in LEGAL_TERMS.items():
            for wrong in wrong_variants:
                start = 0
                while True:
                    idx = text.find(wrong, start)
                    if idx == -1:
                        break
                    findings.append({
                        "found": wrong,
                        "suggested": correct_term,
                        "position": idx,
                    })
                    start = idx + len(wrong)

        findings.sort(key=lambda f: f["position"])
        return findings

    # ── Internal methods ──

    def _check_common_misspellings(self, text: str) -> list[dict]:
        """Check for common misspellings."""
        errors: list[dict] = []

        for wrong, correct in COMMON_MISSPELLINGS.items():
            start = 0
            while True:
                idx = text.find(wrong, start)
                if idx == -1:
                    break

                error_type = "spacing" if " " in correct and " " not in wrong else "spelling"
                errors.append({
                    "original": wrong,
                    "corrected": correct,
                    "position": idx,
                    "type": error_type,
                })
                start = idx + len(wrong)

        return errors

    def _check_spacing_rules(self, text: str) -> list[dict]:
        """Check Korean spacing rules specific to formal documents."""
        errors: list[dict] = []

        # "에따라" -> "에 따라"
        patterns = [
            (re.compile(r"에따라"), "에 따라", "spacing"),
            (re.compile(r"에의해"), "에 의해", "spacing"),
            (re.compile(r"에대한"), "에 대한", "spacing"),
            (re.compile(r"에관한"), "에 관한", "spacing"),
            (re.compile(r"을통해"), "을 통해", "spacing"),
            (re.compile(r"를통해"), "를 통해", "spacing"),
            (re.compile(r"에따른"), "에 따른", "spacing"),
            (re.compile(r"에의한"), "에 의한", "spacing"),
            (re.compile(r"에대해"), "에 대해", "spacing"),
            (re.compile(r"을위해"), "을 위해", "spacing"),
            (re.compile(r"를위해"), "를 위해", "spacing"),
            (re.compile(r"로인해"), "로 인해", "spacing"),
            # 된다/된다 series
            (re.compile(r"되여"), "되어", "grammar"),
            (re.compile(r"하여야"), "해야", "grammar"),
        ]

        for pattern, correction, err_type in patterns:
            for m in pattern.finditer(text):
                errors.append({
                    "original": m.group(),
                    "corrected": correction,
                    "position": m.start(),
                    "type": err_type,
                })

        return errors

    def _check_number_units(self, text: str) -> list[dict]:
        """Check number-unit spacing."""
        errors: list[dict] = []

        for pattern, replacement in NUMBER_UNIT_PATTERNS:
            if replacement is None:
                continue
            for m in pattern.finditer(text):
                corrected = pattern.sub(replacement, m.group())
                if corrected != m.group():
                    errors.append({
                        "original": m.group(),
                        "corrected": corrected,
                        "position": m.start(),
                        "type": "spacing",
                    })

        return errors

    @staticmethod
    def _deduplicate(errors: list[dict]) -> list[dict]:
        """Remove overlapping errors, keeping the first one."""
        if not errors:
            return errors

        result = [errors[0]]
        for e in errors[1:]:
            prev = result[-1]
            prev_end = prev["position"] + len(prev["original"])
            if e["position"] >= prev_end:
                result.append(e)

        return result
