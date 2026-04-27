# 코드 리뷰 보고서

## 요약
- Critical: 3건
- Major: 7건
- Minor: 5건
- Suggestion: 4건

---

## Critical 이슈

### [C-1] 정규식(ReDoS) 인젝션 위험
- 파일: `backend/app/services/search_service.py:51`, `backend/app/services/hwp_service.py:270`
- 설명: 사용자가 `regex: true` 옵션으로 검색할 때, 입력된 정규식 패턴이 검증 없이 `re.compile()`에 전달됩니다. 악의적인 정규식 패턴(예: `(a+)+$`)을 통해 ReDoS(Regular Expression Denial of Service) 공격이 가능합니다. `search_service.py`에서는 `re.error`만 catch하고 있으나, 실행 시간이 매우 긴 패턴은 예외를 발생시키지 않고 CPU를 점유합니다.
- 권장 조치:
  - 정규식 패턴의 길이 제한 (예: 최대 200자)
  - 정규식 실행에 타임아웃 적용 (예: `re2` 라이브러리 사용 또는 별도 스레드에서 타임아웃 처리)
  - 위험한 패턴 감지 로직 추가

### [C-2] API 인증/인가 부재
- 파일: `backend/app/main.py`, `backend/app/routers/documents.py`
- 설명: 모든 API 엔드포인트에 인증/인가 메커니즘이 없습니다. 누구나 문서를 업로드, 수정, 삭제할 수 있으며, 다른 사용자의 문서에도 접근 가능합니다. MVP 단계이더라도 최소한의 인증 계층이 필요합니다.
- 권장 조치:
  - JWT 또는 세션 기반 인증 미들웨어 추가
  - 문서 소유권 모델 추가 (Document에 user_id 필드)
  - 당장 구현이 어려우면, 최소한 API 키 기반 인증이라도 적용

### [C-3] XML External Entity (XXE) 공격 가능성
- 파일: `backend/app/services/hwp_service.py:331`, `backend/app/services/law_service.py:184`
- 설명: `xml.etree.ElementTree.fromstring()`을 사용하여 XML을 파싱하고 있습니다. HWPX 파일 내 악의적인 XML이나 법령 API 응답에 XXE 공격 페이로드가 포함될 경우, 서버의 로컬 파일이 노출되거나 SSRF 공격이 가능합니다. Python의 `ElementTree`는 기본적으로 일부 XXE를 차단하지만, `defusedxml` 라이브러리 사용이 권장됩니다.
- 권장 조치:
  - `defusedxml` 패키지를 설치하고 `defusedxml.ElementTree`로 교체
  - 특히 사용자가 업로드하는 HWPX 파일은 반드시 안전한 파서를 사용

---

## Major 이슈

### [M-1] 프론트엔드-백엔드 API 엔드포인트 불일치 (엑셀 업로드)
- 파일: `frontend/src/lib/api.ts:49-54`, `frontend/src/components/upload/ExcelUpload.tsx:57-59`
- 설명: 프론트엔드에서 엑셀 업로드 시 `/api/documents/${id}/excel-upload` 경로로 요청을 보내지만, 백엔드에는 해당 엔드포인트가 없습니다. 백엔드의 실제 엔드포인트는 `/api/documents/{document_id}/replace/excel`입니다. 이로 인해 엑셀 일괄 교체 기능이 동작하지 않습니다.
- 권장 조치: 프론트엔드의 API 경로를 백엔드 엔드포인트와 일치시키거나, 반대로 백엔드에 해당 경로 추가

### [M-2] 프론트엔드-백엔드 타입 불일치 (법률 검색)
- 파일: `frontend/src/types/law.ts`, `backend/app/routers/law.py:14-18`
- 설명: 백엔드 `LawSearchItem`은 `law_id`, `law_name`, `law_type`, `proclamation_date`, `enforcement_date` 필드를 반환하지만, 프론트엔드 `LawSearchItem`은 `law_id`, `title`, `content_snippet`으로 완전히 다른 필드를 기대합니다. 또한 `LawVerifyResult`도 백엔드(`exists`, `correct_name`, `is_current`, `last_amended`, `article_exists`)와 프론트엔드(`is_valid`, `details`, `suggestions`)가 불일치합니다.
- 권장 조치: 프론트엔드 타입을 백엔드 스키마와 동기화

### [M-3] 프론트엔드-백엔드 타입 불일치 (검색 결과)
- 파일: `frontend/src/types/document.ts:60-64`, `backend/app/schemas/document.py:82-87`
- 설명: 백엔드 `SearchMatch`는 `index`, `line`, `column`, `match`, `context`, `position` 필드를 반환하지만, 프론트엔드 `SearchMatch`는 `text`, `position`, `context`만 정의되어 있습니다. `line`, `column` 등 유용한 정보가 프론트엔드에서 사용되지 않습니다.
- 권장 조치: 프론트엔드 SearchMatch 타입에 누락된 필드 추가

### [M-4] `DocumentDetail` 스키마에 `file_path` 노출
- 파일: `backend/app/schemas/document.py:44`
- 설명: `DocumentDetail` 응답 스키마에 `file_path` 필드가 포함되어 서버 내부 파일 시스템 경로가 클라이언트에 그대로 노출됩니다. 이는 정보 유출 취약점으로 공격자에게 서버 디렉토리 구조를 알려줄 수 있습니다.
- 권장 조치: `DocumentDetail` 스키마에서 `file_path` 필드를 제거하거나, API 응답에서 제외

### [M-5] 파일 업로드 시 파일명 검증 미흡
- 파일: `backend/app/services/document_service.py:44-54`
- 설명: 파일 업로드 시 확장자만 검사하고 파일명 자체의 유효성을 검증하지 않습니다. `../../etc/passwd.hwpx`와 같은 파일명으로 path traversal 공격이 가능할 수 있습니다. 현재 코드에서는 `document_id` 기반 디렉토리 구조를 사용하므로 직접적 위험은 낮지만, `original_filename`이 DB에 저장되어 다른 경로에서 사용될 경우 위험합니다.
- 권장 조치:
  - 파일명을 sanitize하여 경로 구분자(`/`, `\`, `..`) 제거
  - `secure_filename()` 유사 함수 적용

### [M-6] 삭제 API 엔드포인트 누락
- 파일: `backend/app/routers/documents.py`, `frontend/src/lib/api.ts:113-115`
- 설명: 프론트엔드에서 `DELETE /api/documents/{id}` 호출을 하지만, 백엔드 라우터에 해당 DELETE 엔드포인트가 정의되어 있지 않습니다. `document_service.delete_document()`는 구현되어 있으나 라우터에 연결되지 않았습니다.
- 권장 조치: `documents.py` 라우터에 DELETE 엔드포인트 추가

### [M-7] `saveDocument` API가 실제로 내용을 저장하지 않음
- 파일: `backend/app/routers/documents.py:266-277`
- 설명: `POST /api/documents/{id}/save` 엔드포인트는 요청 본문(content)을 받지 않고, 단순히 현재 문서 상태를 반환합니다. 프론트엔드(`api.ts:95-98`)에서는 `{ content }`를 body로 전송하지만 백엔드에서 무시됩니다. 사용자의 에디터 편집 내용이 실제로 저장되지 않습니다.
- 권장 조치: 백엔드 save 엔드포인트에서 request body의 content를 받아 문서를 실제로 업데이트하도록 수정

---

## Minor 이슈

### [m-1] 법령 API URL이 HTTP (비암호화)
- 파일: `backend/app/services/law_service.py:30-31`
- 설명: 법제처 API 호출 시 `http://` 프로토콜을 사용합니다. API 키가 쿼리 파라미터로 전송되므로, 네트워크 상에서 키가 평문으로 노출됩니다.
- 권장 조치: `https://` 프로토콜 사용 가능 여부 확인 후 변경

### [m-2] 임시 파일 정리 미흡
- 파일: `backend/app/services/hwp_service.py:398-433`
- 설명: `_replace_text_sync()`가 호출될 때마다 UUID 기반의 새 HWPX 파일이 생성되지만, 이전 파일이 삭제되지 않습니다. `replace_in_document()`에서 여러 치환을 순차적으로 수행하면 중간 파일들이 디스크에 남습니다. 대량 사용 시 디스크 공간 문제가 발생할 수 있습니다.
- 권장 조치: 치환 완료 후 중간 임시 파일 삭제, 또는 `tempfile` 모듈 활용

### [m-3] 대용량 파일 메모리 이슈
- 파일: `backend/app/routers/documents.py:103`, `backend/app/services/document_service.py:56`
- 설명: 파일 업로드 시 `await file.read()`로 전체 내용을 메모리에 로드합니다. 50MB 제한이 있지만, 동시에 여러 사용자가 대용량 파일을 업로드하면 메모리 부족이 발생할 수 있습니다.
- 권장 조치: 스트리밍 방식으로 파일을 디스크에 저장 (청크 단위 읽기/쓰기)

### [m-4] `replace_all` 파라미터가 백엔드에서 무시됨
- 파일: `frontend/src/lib/api.ts:69-81`, `backend/app/schemas/document.py:97-101`
- 설명: 프론트엔드 `replaceText()`가 `replace_all` 파라미터를 전송하지만, 백엔드 `ReplaceTextRequest` 스키마에 해당 필드가 없어 무시됩니다. 백엔드는 항상 전체 치환을 수행합니다.
- 권장 조치: 백엔드 스키마에 `replace_all` 필드를 추가하고 로직에 반영하거나, 프론트엔드에서 해당 파라미터 제거

### [m-5] `law_service.py`에서 `verify_law` 요청 스키마 불일치
- 파일: `frontend/src/lib/api.ts:126-132`, `backend/app/routers/law.py:98-114`
- 설명: 프론트엔드 `verifyLaw()`가 `{ text, law_id }` body를 전송하지만, 백엔드 `LawVerifyRequest`는 `{ law_name, article_number }` 필드를 기대합니다. 필드명이 완전히 다릅니다.
- 권장 조치: 프론트엔드와 백엔드의 요청 스키마 통일

---

## Suggestion

### [S-1] CORS 설정 강화
- 파일: `backend/app/main.py:24-30`
- 설명: 현재 `allow_methods=["*"]`, `allow_headers=["*"]`로 모든 HTTP 메소드와 헤더를 허용합니다. 프로덕션 배포 시에는 필요한 메소드와 헤더만 명시적으로 허용하는 것이 좋습니다.
- 권장 조치: `allow_methods=["GET", "POST", "PUT", "DELETE"]` 등 필요한 것만 명시

### [S-2] 법률 검색 페이지의 Mock 데이터 폴백 패턴
- 파일: `frontend/src/app/law/page.tsx:31-57`, `frontend/src/app/law/page.tsx:78-92`
- 설명: 법률 검색 시 API 실패 시 하드코딩된 Mock 데이터로 폴백하는 패턴이 프로덕션 코드에 남아 있습니다. 이는 사용자에게 잘못된 정보를 제공할 수 있습니다.
- 권장 조치: Mock 데이터는 개발 환경에서만 사용하도록 분리하거나, 프로덕션에서는 에러 메시지를 표시

### [S-3] DB 마이그레이션 도구 부재
- 설명: SQLAlchemy 모델은 정의되어 있으나, Alembic 등의 DB 마이그레이션 도구가 설정되어 있지 않습니다. 스키마 변경 시 데이터 손실 위험이 있습니다.
- 권장 조치: Alembic 설정 추가 및 초기 마이그레이션 스크립트 생성

### [S-4] 에러 핸들링 전역 일관성
- 파일: `backend/app/main.py`
- 설명: 각 라우터에서 개별적으로 예외를 catch하여 HTTPException으로 변환하고 있습니다. 전역 예외 핸들러를 등록하면 코드 중복을 줄이고 일관된 에러 응답 형식을 보장할 수 있습니다.
- 권장 조치: FastAPI의 `@app.exception_handler()`를 활용한 전역 에러 핸들러 추가

---

## 종합 평가

### 긍정적 측면
- **아키텍처**: 서비스 레이어 패턴이 잘 적용되어 있으며, 라우터/서비스/모델 간 관심사 분리가 적절합니다.
- **코드 품질**: Pydantic 스키마, TypeScript 타입 정의, Zustand 상태 관리 등 현대적인 패턴을 잘 활용하고 있습니다.
- **DB 설계**: SQLAlchemy ORM을 통한 파라미터 바인딩으로 SQL 인젝션이 방지됩니다.
- **버전 관리**: 문서 버전 관리 체계가 잘 설계되어 있습니다.
- **HWP/HWPX 처리**: HWPX XML 파싱 로직이 체계적으로 구현되어 있습니다.
- **UI/UX**: Monaco Editor 통합, Diff 뷰어, 검색/치환 패널 등 편집 관련 UI가 잘 구현되어 있습니다.

### 개선 필요 사항
1. **보안**: 인증/인가 부재(C-2)와 XXE 취약점(C-3)은 배포 전 반드시 해결해야 합니다.
2. **API 정합성**: 프론트엔드-백엔드 간 엔드포인트/타입 불일치가 다수 존재합니다(M-1, M-2, M-3, M-6, M-7). 프론트엔드와 백엔드가 독립적으로 개발된 흔적이 보이며, 통합 테스트가 필요합니다.
3. **핵심 기능 미연결**: 문서 저장(M-7)과 삭제(M-6) 같은 핵심 기능이 실제로 동작하지 않습니다.
4. **리소스 관리**: 임시 파일 정리(m-2)와 대용량 파일 처리(m-3) 개선이 필요합니다.

### MVP 완성도 판정
1단계 MVP의 핵심 기능(HWP/HWPX 처리, 엑셀 일괄 수정, 검색/치환, Diff View) 백엔드 로직은 대부분 구현되어 있으나, **프론트엔드-백엔드 통합이 미완성** 상태입니다. 특히 엑셀 일괄 교체(M-1), 문서 저장(M-7), 문서 삭제(M-6) 경로가 연결되지 않아 실제 E2E 시나리오가 동작하지 않습니다. 이 부분의 수정이 MVP 출시 전 필수입니다.
