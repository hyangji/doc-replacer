# DocReplacer - 컴포넌트 목록 및 디자인 토큰

## 1. 재사용 컴포넌트 목록

### 1.1 레이아웃 컴포넌트

| 컴포넌트명 | Ant Design 매핑 | 설명 | 사용 화면 |
|-----------|-----------------|------|----------|
| `AppLayout` | `Layout` + `Layout.Header` + `Layout.Sider` + `Layout.Content` + `Layout.Footer` | 전체 앱 레이아웃 셸 | 모든 화면 |
| `AppHeader` | `Layout.Header` + `Menu` + `Input.Search` + `Badge` + `Avatar` + `Dropdown` | 상단 헤더 (로고, 검색, 알림, 사용자) | 모든 화면 |
| `AppSider` | `Layout.Sider` + `Menu` (mode="inline") | 좌측 사이드바 네비게이션 | 모든 화면 |
| `PageContainer` | `Breadcrumb` + `Typography.Title` + 커스텀 wrapper | 페이지 공통 컨테이너 (Breadcrumb + 제목 + 콘텐츠) | 모든 화면 |

### 1.2 파일 관련 컴포넌트

| 컴포넌트명 | Ant Design 매핑 | 설명 | 사용 화면 |
|-----------|-----------------|------|----------|
| `FileUploader` | `Upload.Dragger` + `Progress` + `message` | 드래그앤드롭 파일 업로드 영역 | 대시보드, 파일 관리 |
| `FileList` | `Table` + `Tag` + `Button` + `Popconfirm` | 문서 목록 테이블 (정렬, 필터, 페이지네이션) | 대시보드 |
| `FileTypeTag` | `Tag` (color 매핑) | 파일 유형 태그 (HWP=blue, HWPX=cyan, Excel=green) | 대시보드, 파일 관리 |
| `FileStatusTag` | `Tag` (color 매핑) | 파일 상태 태그 (원본=blue, 수정됨=orange, 변환됨=green) | 대시보드 |

### 1.3 편집기 컴포넌트

| 컴포넌트명 | Ant Design / 라이브러리 매핑 | 설명 | 사용 화면 |
|-----------|---------------------------|------|----------|
| `DocumentEditor` | `@monaco-editor/react` (Monaco Editor) | 문서 편집기 메인 영역 | 문서 편집기 |
| `EditorToolbar` | `Space` + `Button` + `Divider` + `Dropdown` + `Tooltip` | 편집기 상단 툴바 | 문서 편집기 |
| `SearchReplacePanel` | 커스텀 (`Input` + `Button` + `Tooltip` + `Badge`) | IDE 스타일 검색/치환 패널 | 문서 편집기 |
| `EditorStatusBar` | 커스텀 Flex div + `Typography.Text` | 하단 상태바 (줄/열, 인코딩, 검색 결과 수) | 문서 편집기 |
| `EditorTabs` | `Tabs` | 열린 문서 탭 (다중 문서 편집 시) | 문서 편집기 |

### 1.4 Diff 관련 컴포넌트

| 컴포넌트명 | Ant Design / 라이브러리 매핑 | 설명 | 사용 화면 |
|-----------|---------------------------|------|----------|
| `DiffViewer` | `react-diff-viewer` (ReactDiffViewer) | 원본/수정본 비교 뷰 | Diff View |
| `DiffToolbar` | `Radio.Group` + `Button` + `Space` | Diff 보기 모드 전환 및 탐색 버튼 | Diff View |
| `ChangeList` | `Table` + `Tag` + `Checkbox` + `Button` | 변경사항 목록 테이블 | Diff View |
| `ChangeTypeTag` | `Tag` | 변경 유형 태그 (수정=orange, 삭제=red, 추가=green) | Diff View |

### 1.5 파일 변환 컴포넌트

| 컴포넌트명 | Ant Design 매핑 | 설명 | 사용 화면 |
|-----------|-----------------|------|----------|
| `ConvertSteps` | `Steps` | 변환 단계 표시 (업로드 > 매핑 > 결과) | 파일 관리 |
| `MappingTable` | `Table` (editable cells) + `Input` + `Form` | 원본/변경 텍스트 매핑 편집 테이블 | 파일 관리 |
| `ConvertOptions` | `Checkbox.Group` + `Card` | 변환 옵션 선택 (형식, 서식 등) | 파일 관리 |
| `ConvertProgress` | `Modal` + `Progress` + `Steps` | 변환 진행률 모달 | 파일 관리 |

### 1.6 법률 검색 컴포넌트

| 컴포넌트명 | Ant Design 매핑 | 설명 | 사용 화면 |
|-----------|-----------------|------|----------|
| `LawSearchBar` | `Radio.Group` + `Input.Search` + `AutoComplete` | 검색 유형 선택 + 검색 입력 | 법률 검색 |
| `LawAdvancedSearch` | `Collapse` + `Checkbox.Group` + `DatePicker.RangePicker` + `Select` | 고급 검색 필터 패널 | 법률 검색 |
| `LawResultList` | `List` + `List.Item` + `Card` + `Pagination` | 검색 결과 목록 | 법률 검색 |
| `LawArticleDetail` | `Card` + `Typography` + `Anchor` | 조문 상세 보기 패널 | 법률 검색 |
| `InsertToDocButton` | `Button` (type="primary") + `Modal` | 문서에 조문 삽입 버튼 | 법률 검색 |

### 1.7 공통 유틸리티 컴포넌트

| 컴포넌트명 | Ant Design 매핑 | 설명 | 사용 화면 |
|-----------|-----------------|------|----------|
| `LoadingOverlay` | `Spin` + 커스텀 wrapper | 페이지/섹션 로딩 오버레이 | 모든 화면 |
| `EmptyState` | `Empty` + `Button` | 데이터 없음 + CTA 버튼 | 모든 화면 |
| `ConfirmAction` | `Popconfirm` 또는 `Modal.confirm` | 위험 액션 확인 대화상자 | 모든 화면 |
| `ErrorBoundary` | `Alert` + `Result` | 에러 발생 시 폴백 UI | 모든 화면 |
| `QuickActions` | `Space` + `Button` (icon 포함) | 퀵 액션 버튼 그룹 | 대시보드 |

---

## 2. 디자인 토큰

### 2.1 색상 (Colors)

Ant Design v5 커스텀 테마 토큰 기반으로 설정합니다.

```typescript
// theme/themeConfig.ts
const themeConfig = {
  token: {
    // 기본 색상
    colorPrimary: '#1677FF',        // Ant Design 기본 파란색
    colorSuccess: '#52C41A',        // 성공 (추가/완료)
    colorWarning: '#FAAD14',        // 경고 (수정됨)
    colorError: '#FF4D4F',          // 에러 (삭제/실패)
    colorInfo: '#1677FF',           // 정보

    // 배경색
    colorBgContainer: '#FFFFFF',    // 카드/패널 배경
    colorBgLayout: '#F0F2F5',       // 전체 레이아웃 배경
    colorBgElevated: '#FFFFFF',     // 드롭다운/모달 배경

    // 텍스트 색상
    colorText: '#000000E0',         // 기본 텍스트 (88% 불투명도)
    colorTextSecondary: '#00000073', // 보조 텍스트
    colorTextTertiary: '#00000040',  // 비활성 텍스트

    // 테두리
    colorBorder: '#D9D9D9',         // 기본 테두리
    colorBorderSecondary: '#F0F0F0', // 보조 테두리
  },
};
```

### 2.2 커스텀 색상 (앱 전용)

| 용도 | 색상 코드 | 설명 |
|------|----------|------|
| Diff 추가 배경 | `#E6FFE6` | 초록색 배경 (추가된 텍스트) |
| Diff 삭제 배경 | `#FFE6E6` | 빨간색 배경 (삭제된 텍스트) |
| Diff 추가 텍스트 | `#237804` | 진한 초록 (추가 텍스트 강조) |
| Diff 삭제 텍스트 | `#CF1322` | 진한 빨강 (삭제 텍스트 강조) |
| 검색 하이라이트 | `#FFFBE6` | 노란색 배경 (검색 결과) |
| 검색 현재 선택 | `#FFD591` | 주황색 배경 (현재 선택 결과) |
| 에디터 배경 | `#1E1E1E` | Monaco Editor 다크 배경 |
| 에디터 텍스트 | `#D4D4D4` | Monaco Editor 기본 텍스트 |
| Sidebar 배경 | `#001529` | 다크 네이비 사이드바 |

### 2.3 타이포그래피 (Typography)

```typescript
const themeConfig = {
  token: {
    // 폰트 패밀리
    fontFamily: "'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",

    // 폰트 크기
    fontSize: 14,                   // 기본 본문
    fontSizeSM: 12,                 // 작은 텍스트 (상태바, 캡션)
    fontSizeLG: 16,                 // 큰 텍스트
    fontSizeXL: 20,                 // 제목

    // 제목 크기 (Typography.Title)
    // h1: 38px - 페이지 메인 제목
    // h2: 30px - 섹션 제목
    // h3: 24px - 서브 섹션
    // h4: 20px - 카드/패널 제목
    // h5: 16px - 소제목

    // 줄 높이
    lineHeight: 1.5714,             // 기본 줄 높이

    // 폰트 굵기
    fontWeightStrong: 600,          // 강조 텍스트
  },
};
```

### 2.4 간격 (Spacing)

```typescript
const themeConfig = {
  token: {
    // 여백/패딩 단위
    padding: 16,                    // 기본 패딩
    paddingXS: 8,                   // 작은 패딩
    paddingSM: 12,                  // 중소 패딩
    paddingLG: 24,                  // 큰 패딩
    paddingXL: 32,                  // 특대 패딩

    // 마진
    margin: 16,                     // 기본 마진
    marginXS: 8,                    // 작은 마진
    marginSM: 12,                   // 중소 마진
    marginLG: 24,                   // 큰 마진
    marginXL: 32,                   // 특대 마진
  },
};
```

### 2.5 레이아웃 수치

| 요소 | 값 | 설명 |
|------|-----|------|
| Header 높이 | 64px | 상단 고정 헤더 |
| Sider 너비 (펼침) | 240px | 사이드바 펼친 상태 |
| Sider 너비 (접힘) | 80px | 사이드바 접힌 상태 |
| Footer 높이 | 48px | 하단 푸터 |
| Content 패딩 | 24px | 콘텐츠 영역 내부 패딩 |
| 최대 콘텐츠 너비 | 1400px | xxl 이상 최대 너비 제한 |
| 카드 간격 | 16px | 카드 사이 간격 (`Row gutter`) |

### 2.6 모서리 반경 (Border Radius)

```typescript
const themeConfig = {
  token: {
    borderRadius: 6,                // 기본 (버튼, 입력, 카드)
    borderRadiusSM: 4,              // 작은 요소 (태그, 뱃지)
    borderRadiusLG: 8,              // 큰 요소 (모달, 드로어)
  },
};
```

### 2.7 그림자 (Box Shadow)

```typescript
const themeConfig = {
  token: {
    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)',
    boxShadowSecondary: '0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 9px 28px 8px rgba(0, 0, 0, 0.05)',
  },
};
```

---

## 3. 컴포넌트 디렉토리 구조

```
frontend/src/components/
├── layout/
│   ├── AppLayout.tsx           # 전체 레이아웃 셸
│   ├── AppHeader.tsx           # 헤더
│   ├── AppSider.tsx            # 사이드바
│   └── PageContainer.tsx       # 페이지 공통 컨테이너
├── editor/
│   ├── DocumentEditor.tsx      # Monaco Editor 래퍼
│   ├── EditorToolbar.tsx       # 편집기 툴바
│   ├── SearchReplacePanel.tsx  # 검색/치환 패널
│   ├── EditorStatusBar.tsx     # 상태바
│   └── EditorTabs.tsx          # 문서 탭
├── diff/
│   ├── DiffViewer.tsx          # Diff 뷰어 래퍼
│   ├── DiffToolbar.tsx         # Diff 툴바
│   ├── ChangeList.tsx          # 변경사항 목록
│   └── ChangeTypeTag.tsx       # 변경 유형 태그
├── file/
│   ├── FileUploader.tsx        # 드래그앤드롭 업로더
│   ├── FileList.tsx            # 파일 목록 테이블
│   ├── FileTypeTag.tsx         # 파일 유형 태그
│   ├── FileStatusTag.tsx       # 파일 상태 태그
│   ├── ConvertSteps.tsx        # 변환 단계 표시
│   ├── MappingTable.tsx        # 매핑 테이블
│   ├── ConvertOptions.tsx      # 변환 옵션
│   └── ConvertProgress.tsx     # 변환 진행률 모달
├── law/
│   ├── LawSearchBar.tsx        # 법률 검색바
│   ├── LawAdvancedSearch.tsx   # 고급 검색 필터
│   ├── LawResultList.tsx       # 검색 결과 목록
│   ├── LawArticleDetail.tsx    # 조문 상세
│   └── InsertToDocButton.tsx   # 문서 삽입 버튼
└── common/
    ├── LoadingOverlay.tsx      # 로딩 오버레이
    ├── EmptyState.tsx          # 빈 상태 표시
    ├── ConfirmAction.tsx       # 확인 대화상자
    ├── ErrorBoundary.tsx       # 에러 바운더리
    └── QuickActions.tsx        # 퀵 액션 버튼 그룹
```

---

## 4. 외부 라이브러리 의존성

| 패키지명 | 버전 | 용도 |
|---------|------|------|
| `antd` | ^5.x | UI 컴포넌트 라이브러리 |
| `@ant-design/icons` | ^5.x | 아이콘 |
| `@monaco-editor/react` | ^4.x | Monaco Editor React 래퍼 |
| `react-diff-viewer-continued` | ^3.x | Diff 뷰어 (react-diff-viewer 후속 유지보수 버전) |
| `@ant-design/cssinjs` | ^1.x | Ant Design CSS-in-JS 엔진 |
