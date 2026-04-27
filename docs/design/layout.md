# DocReplacer - 전체 레이아웃 설계

## 1. 공통 레이아웃 구조

```
+------------------------------------------------------------------+
|                        Header (64px)                             |
|  [Logo] DocReplacer          [검색] [알림] [사용자 아바타]       |
+----------+-------------------------------------------------------+
|          |                                                       |
| Sidebar  |                   Content Area                        |
| (240px)  |                                                       |
|          |              (Breadcrumb 상단 표시)                     |
| [메뉴]   |                                                       |
| 대시보드  |                                                       |
| 문서 편집 |           페이지별 메인 콘텐츠 영역                      |
| Diff 보기 |                                                       |
| 파일 관리 |              min-height: calc(100vh - 64px - 48px)      |
| 법률 검색 |                                                       |
|          |                                                       |
|          |                                                       |
+----------+-------------------------------------------------------+
|                        Footer (48px)                             |
|           (c) DocReplacer v1.0 | 도움말 | 문의                   |
+------------------------------------------------------------------+
```

### 1.1 Header

- **컴포넌트**: `Ant Design Layout.Header`
- **높이**: 64px
- **배경색**: `#001529` (Ant Design 기본 다크 테마)
- **구성 요소**:
  - 좌측: 로고 + 시스템명 "DocReplacer"
  - 중앙: 글로벌 검색바 (`Input.Search`, 너비 400px)
  - 우측: 알림 아이콘 (`Badge` + `BellOutlined`), 사용자 드롭다운 (`Dropdown` + `Avatar`)

### 1.2 Sidebar

- **컴포넌트**: `Ant Design Layout.Sider`
- **너비**: 240px (접힌 상태 80px)
- **접기/펼치기**: `Sider`의 `collapsible` 속성 사용
- **배경색**: `#001529`
- **메뉴 컴포넌트**: `Menu` (mode="inline", theme="dark")
- **메뉴 항목**:

| 순서 | 아이콘               | 메뉴명     | 경로               |
|------|---------------------|-----------|-------------------|
| 1    | `DashboardOutlined` | 대시보드    | `/`               |
| 2    | `EditOutlined`      | 문서 편집   | `/editor`         |
| 3    | `DiffOutlined`      | Diff 보기  | `/diff`           |
| 4    | `UploadOutlined`    | 파일 관리   | `/files`          |
| 5    | `BookOutlined`      | 법률 검색   | `/law-search`     |

### 1.3 Content Area

- **컴포넌트**: `Ant Design Layout.Content`
- **패딩**: 24px
- **배경색**: `#f0f2f5`
- **상단**: `Breadcrumb` 컴포넌트로 현재 위치 표시
- **최소 높이**: `calc(100vh - 64px - 48px)`

### 1.4 Footer

- **컴포넌트**: `Ant Design Layout.Footer`
- **높이**: 48px
- **텍스트 정렬**: 중앙
- **내용**: 저작권, 버전 정보, 도움말 링크

---

## 2. 네비게이션 구조

### 2.1 주요 네비게이션 (Sidebar 메뉴)

```
대시보드 (/)
├── 최근 문서
├── 파일 업로드
└── 퀵 액션

문서 편집 (/editor)
├── /editor/:documentId    -- 특정 문서 편집
└── /editor/new            -- 새 문서

Diff 보기 (/diff)
└── /diff/:documentId      -- 특정 문서 변경사항

파일 관리 (/files)
├── /files/upload           -- 파일 업로드/변환
└── /files/convert          -- 파일 변환

법률 검색 (/law-search)
└── /law-search/:articleId  -- 조문 상세
```

### 2.2 보조 네비게이션

- **Breadcrumb**: 각 페이지 상단, 현재 경로 표시
- **탭 네비게이션**: 문서 편집기 내에서 열린 문서 간 전환 (`Tabs` 컴포넌트)
- **컨텍스트 메뉴**: 문서 목록에서 우클릭 시 (`Dropdown` 컴포넌트)

### 2.3 페이지 간 흐름

```
대시보드 ──[문서 클릭]──> 문서 편집기
대시보드 ──[업로드 클릭]──> 파일 업로드/변환
문서 편집기 ──[Diff 버튼]──> Diff View
문서 편집기 ──[법률 검색 버튼]──> 법률 검색 (Drawer)
파일 업로드 ──[변환 완료]──> 문서 편집기
법률 검색 ──[삽입 버튼]──> 문서 편집기 (커서 위치에 삽입)
```

---

## 3. 반응형 브레이크포인트

Ant Design의 Grid 시스템 기반 브레이크포인트를 사용합니다.

| 브레이크포인트 | 너비         | Sidebar 상태 | 레이아웃 변화                     |
|-------------|-------------|-------------|--------------------------------|
| `xs`        | < 576px     | 숨김 (Drawer) | 단일 컬럼, 햄버거 메뉴             |
| `sm`        | >= 576px    | 숨김 (Drawer) | 단일 컬럼, 햄버거 메뉴             |
| `md`        | >= 768px    | 접힌 상태 (80px) | 아이콘만 표시                    |
| `lg`        | >= 992px    | 펼친 상태 (240px) | 기본 레이아웃                   |
| `xl`        | >= 1200px   | 펼친 상태 (240px) | 기본 레이아웃, 여백 증가          |
| `xxl`       | >= 1600px   | 펼친 상태 (240px) | 최대 콘텐츠 너비 1400px, 중앙 정렬 |

### 3.1 모바일 대응 (xs, sm)

- Sidebar를 `Drawer` 컴포넌트로 전환 (왼쪽에서 슬라이드)
- Header에 햄버거 메뉴 버튼 (`MenuOutlined`) 추가
- 문서 편집기의 검색/치환 패널을 하단 `Drawer`로 변경
- Diff View를 좌우 분할 대신 상하 분할 또는 탭 전환 방식으로 변경

### 3.2 태블릿 대응 (md)

- Sidebar 접힌 상태 (아이콘만 표시, 80px)
- 문서 편집기의 검색/치환 패널은 우측 패널 유지
- Diff View 좌우 분할 유지

### 3.3 데스크톱 (lg 이상)

- 기본 레이아웃 유지
- `xxl` 이상에서 콘텐츠 최대 너비 제한 (1400px)

---

## 4. 레이아웃 구현 참고

### 4.1 Next.js App Router 레이아웃 구조

```
app/
├── layout.tsx              -- 루트 레이아웃 (Header + Sider + Footer)
├── page.tsx                -- 대시보드
├── editor/
│   ├── layout.tsx          -- 편집기 전용 레이아웃 (Footer 숨김)
│   ├── page.tsx            -- 편집기 메인
│   └── [documentId]/
│       └── page.tsx        -- 특정 문서 편집
├── diff/
│   └── [documentId]/
│       └── page.tsx        -- Diff 뷰
├── files/
│   ├── page.tsx            -- 파일 관리
│   └── upload/
│       └── page.tsx        -- 업로드/변환
└── law-search/
    └── page.tsx            -- 법률 검색
```

### 4.2 편집기 화면 특수 레이아웃

문서 편집기 화면은 최대한 넓은 편집 영역이 필요하므로:
- Footer 숨김
- Content 패딩 제거 (0px)
- Sidebar 접기 가능 상태 유지
- 전체 화면 모드 지원 (`Fullscreen` 토글 버튼)
