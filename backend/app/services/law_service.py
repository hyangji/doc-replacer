"""국가법령정보 Open API 연동 서비스.

법제처 국가법령정보센터(https://open.law.go.kr) API를 통해
법령 검색, 조문 상세 조회, 법률 인용 검증 기능을 제공합니다.

API 응답은 XML 형식이며, httpx async 클라이언트로 호출합니다.
"""

import logging
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as SafeET
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LawServiceError(Exception):
    """Base exception for law service errors."""


class LawApiError(LawServiceError):
    """Raised when the law API call fails."""


class LawService:
    """국가법령정보 Open API 연동 서비스."""

    BASE_URL = "http://www.law.go.kr/DRF/lawSearch.do"
    DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"

    def __init__(self) -> None:
        self._api_key = settings.LAW_API_KEY
        self._timeout = 10.0

    async def search_law(
        self,
        query: str,
        search_type: str = "law",
        page: int = 1,
        display: int = 20,
    ) -> list[dict]:
        """법령 검색 (법령명, 조문, 키워드).

        Args:
            query: 검색어.
            search_type: 검색 유형 - "law"(법령명), "jo"(조문), "key"(키워드).
            page: 페이지 번호 (1부터).
            display: 한 페이지당 결과 수.

        Returns:
            List of {
                "law_id": str,
                "law_name": str,
                "law_type": str,
                "proclamation_date": str,
                "enforcement_date": str,
            }
        """
        params = {
            "OC": self._api_key,
            "target": search_type,
            "type": "XML",
            "query": query,
            "display": str(display),
            "page": str(page),
        }

        xml_text = await self._call_api(self.BASE_URL, params)
        return self._parse_search_response(xml_text)

    async def get_law_detail(self, law_id: str) -> dict:
        """특정 법령의 조문 상세 조회.

        Args:
            law_id: 법령 MST (법령ID).

        Returns: {
            "law_name": str,
            "law_id": str,
            "proclamation_date": str,
            "articles": [{
                "number": str,
                "title": str,
                "content": str,
            }],
        }
        """
        params = {
            "OC": self._api_key,
            "target": "law",
            "type": "XML",
            "MST": law_id,
        }

        xml_text = await self._call_api(self.DETAIL_URL, params)
        return self._parse_detail_response(xml_text, law_id)

    async def verify_law_reference(
        self,
        law_name: str,
        article_number: str | None = None,
    ) -> dict:
        """문서 내 법률 인용의 정확성 검증.

        Args:
            law_name: 인용된 법령명.
            article_number: 인용된 조문 번호 (선택).

        Returns: {
            "exists": bool,
            "correct_name": str,
            "is_current": bool,
            "last_amended": str,
            "article_exists": bool | None,
        }
        """
        # Search for the law by name
        results = await self.search_law(law_name, search_type="law")

        if not results:
            return {
                "exists": False,
                "correct_name": "",
                "is_current": False,
                "last_amended": "",
                "article_exists": None,
            }

        # Find best match
        best_match = self._find_best_match(law_name, results)

        result = {
            "exists": True,
            "correct_name": best_match["law_name"],
            "is_current": True,  # Listed in API = currently in force
            "last_amended": best_match.get("proclamation_date", ""),
            "article_exists": None,
        }

        # Verify article if specified
        if article_number and best_match.get("law_id"):
            try:
                detail = await self.get_law_detail(best_match["law_id"])
                articles = detail.get("articles", [])
                article_exists = any(
                    a["number"] == article_number or a["number"] == f"제{article_number}조"
                    for a in articles
                )
                result["article_exists"] = article_exists
            except LawApiError:
                result["article_exists"] = None

        return result

    # ── Internal methods ──

    async def _call_api(self, url: str, params: dict) -> str:
        """Call the law API and return the XML response text."""
        if not self._api_key:
            raise LawApiError(
                "법령 API 키가 설정되지 않았습니다. "
                "환경변수 LAW_API_KEY를 설정해 주세요."
            )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException:
            raise LawApiError("법령 API 요청 시간이 초과되었습니다.")
        except httpx.HTTPStatusError as e:
            raise LawApiError(f"법령 API 오류: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            raise LawApiError(f"법령 API 연결 실패: {e}")

    def _parse_search_response(self, xml_text: str) -> list[dict]:
        """Parse the XML search response from the law API."""
        results: list[dict] = []

        try:
            root = SafeET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("법령 검색 XML 파싱 실패: %s", e)
            return results

        # The API returns <law> elements under the root
        for law_el in root.iter("law"):
            law_id = self._get_text(law_el, "법령MST") or self._get_text(law_el, "법령ID") or ""
            law_name = self._get_text(law_el, "법령명한글") or self._get_text(law_el, "법령명") or ""
            law_type = self._get_text(law_el, "법령종류") or ""
            proclamation_date = self._get_text(law_el, "공포일자") or ""
            enforcement_date = self._get_text(law_el, "시행일자") or ""

            if law_name:
                results.append({
                    "law_id": law_id,
                    "law_name": law_name,
                    "law_type": law_type,
                    "proclamation_date": proclamation_date,
                    "enforcement_date": enforcement_date,
                })

        return results

    def _parse_detail_response(self, xml_text: str, law_id: str) -> dict:
        """Parse the XML detail response for a specific law."""
        try:
            root = SafeET.fromstring(xml_text)
        except ET.ParseError as e:
            raise LawApiError(f"법령 상세 XML 파싱 실패: {e}")

        law_name = self._get_text(root, "법령명한글") or self._get_text(root, "법령명") or ""
        proclamation_date = self._get_text(root, "공포일자") or ""

        articles: list[dict] = []
        for article_el in root.iter("조문단위"):
            number = self._get_text(article_el, "조문번호") or ""
            title = self._get_text(article_el, "조문제목") or ""
            content = self._get_text(article_el, "조문내용") or ""

            if number or content:
                articles.append({
                    "number": number,
                    "title": title,
                    "content": content,
                })

        return {
            "law_name": law_name,
            "law_id": law_id,
            "proclamation_date": proclamation_date,
            "articles": articles,
        }

    @staticmethod
    def _get_text(element: ET.Element, tag: str) -> str | None:
        """Safely get text from a child element."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    @staticmethod
    def _find_best_match(query: str, results: list[dict]) -> dict:
        """Find the best matching law from search results."""
        query_normalized = query.strip().replace(" ", "")

        # Exact match first
        for r in results:
            if r["law_name"].replace(" ", "") == query_normalized:
                return r

        # Partial match (contains)
        for r in results:
            if query_normalized in r["law_name"].replace(" ", ""):
                return r

        # Return first result as fallback
        return results[0]
