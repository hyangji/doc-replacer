# DocReplacer - 도시계획 제안서 문서 관리 시스템

## 프로젝트 개요
도시계획 제안서의 반복적 문서 수정을 자동화하고 법률 문서 정확성을 검증하는 웹 시스템.

## 기술 스택
- **프론트엔드**: Next.js 15, React 19, TypeScript, Ant Design, Monaco Editor, react-diff-viewer
- **백엔드**: Python 3.12, FastAPI, SQLAlchemy, Celery
- **HWP 처리**: Java hwplib (HWP) + python-hwpx (HWPX) - 2단계 파이프라인
- **엑셀 처리**: openpyxl, pandas
- **파일 변환**: python-docx (Word), reportlab (PDF)
- **법률 API**: 국가법령정보 Open API (법제처, 무료)
- **DB**: PostgreSQL, Redis
- **인프라**: Docker, Docker Compose

## 디렉토리 구조
```
doc-replacer/
├── frontend/          # Next.js 프론트엔드
│   └── src/
│       ├── app/       # App Router 페이지
│       ├── components/# React 컴포넌트
│       ├── lib/       # 유틸리티, API 클라이언트
│       └── types/     # TypeScript 타입 정의
├── backend/           # Python FastAPI 백엔드
│   └── app/
│       ├── routers/   # API 라우터
│       ├── services/  # 비즈니스 로직
│       ├── models/    # DB 모델
│       └── schemas/   # Pydantic 스키마
├── docs/              # 문서
└── docker-compose.yml # 전체 서비스 오케스트레이션
```

## 개발 규칙
- 커밋 메시지는 한국어로 작성
- API는 REST 기반, 응답은 JSON
- 프론트엔드 컴포넌트는 함수형 + hooks 패턴
- 백엔드는 async/await 기반
- 모든 API에 에러 핸들링 필수
- 파일 업로드 최대 50MB

## 개발 단계
- 1단계 (MVP): HWP/HWPX 처리, 엑셀 일괄 수정, 검색/치환, Diff View
- 2단계: 법률 API 연동, 법률 검색 화면, 오타 검출
- 3단계: 파일 변환 (Word, PDF), 금액 자동 변환/계산
- 4단계: 버전 관리, 다중 파일 처리, 변경 보고서, PDF 내보내기

## 명령어
- 프론트엔드: `cd frontend && npm run dev` (port 3000)
- 백엔드: `cd backend && uvicorn app.main:app --reload` (port 8000)
- Docker: `docker-compose up -d`
