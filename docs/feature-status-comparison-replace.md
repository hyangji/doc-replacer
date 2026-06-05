# 엑셀 대비표 → HWP 표 일괄수정 — 기능 현황 문서

> 최종 갱신: 2026-06-05
> 상태: **핵심 흐름 동작(로컬 검증 완료)** / 일부 한계·미커밋
> 관련 문서: [구조분석](excel-table-replacement-analysis.md), [변경표시 UX 리서치](research-change-preview-ux.md)

---

## 0. 한 줄 요약

이미 작성된 **HWP 고시문**에, 고객이 준 **엑셀 대비표(기정→변경후)** 의 수치를 일괄 적용하고, **표·서식이 보존된 수정본 HWP**를 받는 기능. 무엇이 바뀌는지 **셀 단위로 확인**하고 적용 전 검토 가능.

---

## 1. 전체 사용자 흐름 (현재 동작)

```
HWP 업로드
  → [대비표 일괄 수정] 탭: 엑셀 업로드 → 미리보기(교체쌍 + 매칭수 안전태그 + 구간현황)
  → 안전 항목 자동선택 + 사용자 선택 → 적용(미리보기 버전 생성)
  → [Diff 비교] 탭
       · 비교 모드 : 텍스트 줄단위 diff
       · 편집 모드 : 텍스트 + 인라인(단어) 하이라이트, 직접 수정/되돌리기
       · 문서 모드 : 표 보존 HTML 원본|수정본 나란히 + 바뀐 셀 색칠 + 좌우 스크롤 동기화
  → [수정본 HWP 다운로드] : 표 보존된 .hwp 파일
```

---

## 2. 구현된 백엔드 (FastAPI)

### 엔드포인트
| 메서드/경로 | 역할 |
|---|---|
| `POST /api/documents/{id}/replace/comparison/preview` | 대비표 엑셀 파싱 → 교체쌍 + HWP 매칭수 + 구간현황(sections) |
| `POST /api/documents/{id}/replace` | 선택 교체쌍 적용 → **미리보기 버전** 생성(본문 즉시 갱신 안 함) |
| `GET /api/documents/{id}/diff` | 원본(v1) vs **최신 버전** 텍스트 diff |
| `POST /api/documents/{id}/revert?version=N` | 특정 버전으로 되돌리기 |
| `GET /api/documents/{id}/download?version=N` | 표 보존 수정본 HWP 다운로드(한글 파일명 RFC5987) |
| `GET /api/documents/{id}/html?version=N` | HWP→표 보존 HTML `{html}` |
| `GET /api/documents/{id}/html/compare?base=&target=` | 셀/단어 단위 비교 HTML `{original_html, modified_html}` (바뀐 곳 `class="hwp-changed"`) |

### 서비스
- **`excel_service.py`**
  - `parse_comparison_table_excel` / `_v2` — 시트 5종(5.나/7/8.가/8.나/8.다) 전용 파서. 콤마 정규화(`184636`↔`184,636`), 증감(`감)`/`증)`)·동일값 제외.
  - 8.다 다중 하위표(도로 총괄표/공원·녹지 총괄/녹지 결정조서) + **구간현황 메타**(parsed/empty/skipped).
  - 시트 7 교차표 라벨 보강: `field_name = "지목별 현황 · 답 · 면적(㎡)"` 형태.
  - 총 73건 추출(고시문 샘플 기준).
- **`hwp_service.py`**
  - `render_hwp_to_html` — 본문 순서대로 `<p>`+`<table>`(병합셀 colspan/rowspan). 50표 정상.
  - `render_hwp_compare_html` — 원본·수정본 셀/단어 비교, 바뀐 곳 `hwp-changed`.
  - `replace_text` / `_replace_text_in_hwp_bytes` — HWP 바이너리 in-place 텍스트 교체(표·서식 보존).

### 스키마
`ComparisonChangeItem`, `ComparisonSheetResult`, `ComparisonPreviewResponse`, `ComparisonSectionInfo`, `DocumentHtmlResponse`, `DocumentCompareHtmlResponse`.

---

## 3. 구현된 프론트엔드 (Next.js)

- **`components/upload/ComparisonUpload.tsx`** — 대비표 업로드/미리보기/적용. 매칭수 태그(안전/주의/매칭없음), 안전(=매칭1) 자동선택, **표별 그룹핑 + 항목명 노출**, 구간 처리현황 패널(미처리 경고).
- **`components/diff/DiffViewer.tsx`** — 비교/편집/**문서** 3모드. 편집모드 인라인 단어 하이라이트, 문서모드 셀 하이라이트(원본 빨강/수정본 초록)+좌우 스크롤 동기화. "수정본 HWP 다운로드" 버튼.
- **`app/editor/[id]/page.tsx`** — 탭: 편집 / 대비표 일괄 수정 / Diff 비교. (구 "엑셀 일괄 교체" 탭은 제거)
- **`lib/api.ts`** — `previewComparison`, `applyReplacements`, `downloadDocument`, `getDocumentHtml`, `getDocumentCompareHtml`.

---

## 4. HWP 바이너리 처리 핵심 지식 (재현/유지보수용)

- **압축 스트림 구조**: `BodyText/SectionN` = raw deflate(-15) **+ 8바이트 트레일러(CRC32(해제본) LE + 해제길이 LE)**. 교체 후 **트레일러 CRC/len 재계산 필수**. (이걸 빼고 0패딩 → 한글 "손상/변조" 경고. 수정 완료)
- **olefile 제약**: 스트림 크기를 키우지 못함. 재압축이 원본 스트림보다 커지면 에러(현재는 deflate 여유분 내 흡수). 동일크기 유지 위해 유효 deflate(빈 stored 블록)로 정확히 패딩.
- **병합셀**: `HWPTAG_LIST_HEADER`(72) payload — col=byte8, row=byte10, colSpan=byte12, rowSpan=byte14 (UINT16 LE).
- **문단 메타**(길이변경 교체 시 보정): `PARA_HEADER`(66) nChars=`u32[0]&0x7FFFFFFF`(상위비트 플래그 보존); `PARA_CHAR_SHAPE`(68) stride 8=(pos u32, shapeId u32); `PARA_LINE_SEG`(69) stride 36, start=int32@0. 교체 지점 이후 위치만 delta 시프트.
- **위치 단위**: printable WCHAR=1, 단순제어(0/10/13)=1, 확장제어=8(제어1+인라인14B=7).

---

## 5. ⚠️ 핵심 한계 / 알려진 이슈

1. **전역 텍스트 치환 (셀 단위 아님)** — `"2"`를 바꾸면 문서의 **모든 "2"** 가 대상. 짧은/중복 숫자는 위험 → **매칭수 "주의" 태그로 회피**(자동선택 제외, 사용자 직접 판단). 실질적으로 **매칭=1 값만 안전**.
   - **→ 다음 핵심 과제: 셀 단위 타겟 교체**(표·셀 위치를 특정해 그 셀만 교체). 그래야 짧은 숫자도 안전.
2. **길이변경 교체** — `69.1→69` 등 문단 메타 보정 구현했고 구조검증 통과. **한글 실파일 최종 확인 대기 중**.
3. **8.다 칼럼 라벨** — `○ 도로 총괄표 합계`가 연장/면적/개소 칼럼 구분 안 됨(같은 라벨 반복). 보강 필요.
4. **저장(확정) HWPX 전용 잔재** — `save_document_content`가 HWPX만 허용. HWP 확정은 다운로드/버전 승격으로 우회 중. 정리 필요.
5. **미커밋** — 이번 세션 변경 다수 미커밋 상태.

---

## 6. 다음 작업 (우선순위)

- [ ] (확인) 길이변경 교체 한글 정상 여부 — `바탕화면/고시문 샘플_길이변경테스트.hwp`
- [ ] **셀 단위 타겟 교체** 설계/구현 (전역치환 → 위치 특정). 짧은 숫자 안전화 + 매칭수 의존 축소.
- [ ] 8.다 칼럼 라벨 보강
- [ ] 변경 커밋(한국어 메시지)
- [ ] (선택) 변경항목 클릭 → 문서 위치 점프

---

## 7. 로컬 실행

```
백엔드: cd backend && uvicorn app.main:app --reload   # 8000
프론트: cd frontend && npm run dev                    # 3000  (.env.local: NEXT_PUBLIC_API_URL=http://localhost:8000)
```

테스트: 문서 업로드 → 대비표 탭 → `고시문 샘플.xlsx` → 적용 → Diff 비교 "문서" 모드 → 수정본 HWP 다운로드.

## 8. 리서치 결론 (요약)

업계 best practice = **맥락(표›행›값) + 인플레이스 미리보기 + 클릭 점프 + 셀 단위 before/after**. 한국 레퍼런스 `kordoc`(공무원 제작 HWP 셀단위 비교). 상세: [research-change-preview-ux.md](research-change-preview-ux.md).
