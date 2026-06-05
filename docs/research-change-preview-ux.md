# 리서치: 문서 일괄수정 도구의 "변경 내용 표시(Change Preview)" 방식

> 작성일: 2026-06-05
> 방법: 심층 리서치(6개 검색 각도, 24개 출처, 87개 주장 추출 → 25개 교차검증 → 21개 확인 / 4개 기각)
> 목적: DocReplacer의 "엑셀 대비표 → HWP 표 일괄수정"에서 사용자가 **무엇이 바뀌는지** 명확히 알게 하는 best practice 조사 및 현재 방식 평가

---

## 핵심 결론 (TL;DR)

업계 우수 도구들은 "값 목록(`184,636→184,110`)"만 제시하지 않는다. 검증된 best practice는 4가지를 함께 제공:

> **① 맥락(표 › 행 › 칼럼)과 함께 + ② 인플레이스 미리보기(어디가 바뀌는지) + ③ 클릭 점프 변경목록 + ④ 셀 단위 before/after**

가장 직접적인 레퍼런스: **`kordoc`** — 광진구 공무원이 만든 HWP/HWPX 셀 단위 비교 오픈소스. 우리가 가려는 방향이 한국 행정문서에서 실증됨.

---

## 1. 도구 카테고리 — 우리는 "비교 × 자동화"의 하이브리드

| 카테고리 | 대표 제품 | 하는 일 | 우리와 차이 |
|---|---|---|---|
| 문서 비교/레드라인 | Litera Compare, Draftable, Word 비교 | 완성 문서 A·B 차이를 레드라인으로 | 우리는 "비교"가 아니라 "엑셀로 수정+적용" |
| 메일머지/문서자동화 | Word Mail Merge, HotDocs, ONLYOFFICE | 빈 템플릿에 데이터 채워 새 문서 생성 | 우리는 이미 완성된 문서를 고침 |

- 우리 케이스와 정확히 일치하는 기성품은 드묾(medium). 두 카테고리의 UX 패턴을 **합성** 필요.
- ⚠️ 기각: "메일머지는 사용된 필드를 전혀 안 보여준다"(0-3), "기존 문서 수정은 특정 제품만 가능"(0-3) — 기존 문서 수정 도구는 여럿 존재.

## 2. 검증된 UX 패턴 (각 3-0 만장일치)

- **인플레이스 + side-by-side 보완**: Draftable 3-pane(원본｜수정본｜레드라인). 레드라인만으론 맥락 부족.
  - ⚠️ 기각(0-3): "단일 레드라인이 나란히보기보다 효율적" → 나란히 비교는 여전히 중요.
- **필드 위치 하이라이트 + 값 미리보기 토글**: HotDocs "Highlight Fields", ONLYOFFICE "Highlight merge fields" + "Preview results".
- **클릭 점프 변경목록 + 항목별 accept/reject**: Draftable Change List, Word 변경내용 추적.
- **표 셀 단위 차이 표시** + Office "바인딩"으로 표를 헤더·셀 단위로 지정.

## 3. 핵심 레퍼런스: `kordoc` (한국 HWP 특화)

- github.com/chrisryugj/kordoc — 광진구 공무원 제작 오픈소스.
- HWP/HWPX를 IR(중간표현)로 파싱 → `diffTableCells`가 표를 셀 위치별 순회하며 before/after 분류.
- 한국 행정문서에서 **셀 단위 비교가 평문 diff 한계를 직접 극복**함을 실증(3-0). 비교 전용 도구라 패턴만 이식 가능.

## 4. 현재 DocReplacer 방식 평가

| 우리 방식 | 평가 |
|---|---|
| 값 쌍 추출(기정→변경후) | ✅ 방향 맞음 |
| match_count 안전/주의 태그 | 🟡 위험관리엔 유용하나 "어디"인지 못 알려줌 |
| 전문(全文) 텍스트 줄 diff | ❌ 표 문서엔 부적합 — best practice는 셀 단위 |
| 맥락 부재 | ❌ 핵심 약점(사용자 불만 원인) |

## 5. 권고 (HWP 제약 감안, 우선순위 순)

1. **맥락 있는 변경목록**: `[표 5.나] 산업시설용지 › 면적: 184,636 → 184,110`. (이미 가진 시트명+field_name 표시만 하면 됨. 7번·8.다 칼럼 라벨은 파서 보강)
2. **클릭 점프**: 항목 클릭 시 문서 해당 위치로 이동 + 주변 표/문장 맥락 표시.
3. **인플레이스 미리보기**: 적용 전 문서 안에서 어디가 바뀌는지 하이라이트.
4. **전문 diff → 셀 단위 before/after** 교체(kordoc 패턴).
5. **항목별 accept/reject** + 다중매칭은 셀 좌표로 구분.

## 제약 메모

- 우리는 HWP 바이너리를 직접 수정(표·서식 보존 OK)하지만, 추출 텍스트는 평문이라 "셀 좌표" 맥락은 표 추출(`extract_tables`) 결과와 연계해야 함.
- 1번(표시 개선)이 노력 대비 효과 최대 — 이미 `시트+항목명` 보유.

## 출처 (검증)

- kordoc: https://github.com/chrisryugj/kordoc
- Draftable: https://www.draftable.com/compare , https://help.draftable.com/hc/en-us/articles/19002235946265-Redline-comparisons
- HotDocs: https://help.hotdocs.com/developer/webhelp/Assembling_Documents_2/assemdoc2_preview_the_assembled_text_document.htm
- ONLYOFFICE Mail Merge: https://helpcenter.onlyoffice.com/docs/userguides/document_editor/UseMailMerge.aspx
- LibreOffice redlining: https://help.libreoffice.org/latest/en-US/text/shared/guide/redlining.html
- Litera Compare: https://www.litera.com/products/litera-compare
- MS Office Add-in bindings: https://learn.microsoft.com/en-us/office/dev/add-ins/develop/bind-to-regions-in-a-document-or-spreadsheet
- 한국 HWP 자동화: https://wikidocs.net/261641 , https://wikidocs.net/257896
