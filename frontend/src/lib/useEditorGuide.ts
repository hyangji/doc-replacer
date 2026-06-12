'use client';

/**
 * 편집기 인앱 사용 가이드 (driver.js 기반) — 상태 적응형
 *
 * portal 프로젝트의 useSqlEditorGuide.js(Vue) 패턴을 React 훅으로 옮긴 것.
 * driver.js 자체는 프레임워크 무관(vanilla)이라 그대로 사용한다.
 *
 * 핵심: 이 앱은 단계마다 데이터(원본/대비표 적용)가 있어야 화면이 생기므로,
 *  - 적용 전(원본 상태): 짧은 "오리엔테이션" — 탭 + 대비표 올리는 법 + 안전/주의 예시 +
 *    "적용하면 Diff/다운로드에서 결과를 봅니다"(말로만). 빈 화면으로 넘어가지 않는다.
 *  - 적용 후: 실제 화면 "풀 투어" — 진짜 결과 표(안전/주의 태그) · Diff · 다운로드까지 강조.
 */
import { useCallback, useEffect, useRef } from 'react';
import { driver, type Driver, type DriveStep } from 'driver.js';
import 'driver.js/dist/driver.css';

interface UseEditorGuideOptions {
  /** 탭 전환 함수(page.tsx의 setActiveTab) */
  setActiveTab: (key: string) => void;
  /** 대비표가 적용된 상태인지(= 풀 투어 / 오리엔테이션 분기) */
  isApplied: boolean;
}

// 지정 셀렉터의 DOM 요소가 나타날 때까지 대기 (비동기 컴포넌트 렌더 대비)
function waitForElement(selector: string, timeout = 2000): Promise<Element | null> {
  return new Promise((resolve) => {
    const found = document.querySelector(selector);
    if (found) return resolve(found);
    const start = performance.now();
    const timer = window.setInterval(() => {
      const el = document.querySelector(selector);
      if (el || performance.now() - start > timeout) {
        window.clearInterval(timer);
        resolve(el ?? null);
      }
    }, 50);
  });
}

// 안전/주의/매칭없음 태그 예시(실제 태그 모양을 popover 안에 그대로 재현)
const TAG_LEGEND_HTML =
  '<div style="margin-top:8px;line-height:1.9;">' +
  '<span style="display:inline-block;background:#f6ffed;color:#389e0d;border:1px solid #b7eb8f;padding:0 6px;border-radius:4px;font-size:12px;">✓ 안전</span> ' +
  '문서에서 <b>딱 1곳</b>만 일치 → <b>자동 선택</b>. 안심하고 적용.<br>' +
  '<span style="display:inline-block;background:#fff7e6;color:#d46b08;border:1px solid #ffd591;padding:0 6px;border-radius:4px;font-size:12px;">⚠ 주의 N건</span> ' +
  '<b>여러 곳</b> 일치 → 다른 곳도 같이 바뀔 수 있어 <b>직접 확인 후</b> 선택.<br>' +
  '<span style="display:inline-block;background:#fff1f0;color:#cf1322;border:1px solid #ffa39e;padding:0 6px;border-radius:4px;font-size:12px;">매칭없음</span> ' +
  '문서에서 값을 못 찾음 → 선택 불가.' +
  '</div>';

export function useEditorGuide({ setActiveTab, isApplied }: UseEditorGuideOptions) {
  const driverRef = useRef<Driver | null>(null);
  // startGuide가 매번 새로 만들어지지 않게, 최신 isApplied는 ref로 읽는다.
  const isAppliedRef = useRef(isApplied);
  isAppliedRef.current = isApplied;

  // 언마운트 시 진행 중이던 가이드 driver 정리(잔여 오버레이 방지)
  useEffect(() => {
    return () => {
      driverRef.current?.destroy();
      driverRef.current = null;
    };
  }, []);

  const startGuide = useCallback(() => {
    if (driverRef.current) {
      driverRef.current.destroy();
      driverRef.current = null;
    }

    let driverObj: Driver;

    // ── 오리엔테이션(적용 전): 빈 화면이라 구조 + 첫 행동 + 안전/주의 예시만 ──
    const orientationSteps: DriveStep[] = [
      {
        element: '.ant-tabs-nav', // 탭 버튼 줄만 강조(본문 제외)
        popover: {
          title: '작업 흐름 (3개 탭)',
          description:
            '이 3개 탭으로 작업합니다.<br>' +
            '<b>미리보기</b>(현재 문서) · <b>대비표 일괄 수정</b> · <b>Diff 비교</b><br>' +
            "원본 HWP는 '문서 작업' 화면에서 업로드합니다.",
          side: 'bottom',
          align: 'center',
          onNextClick: async () => {
            setActiveTab('comparison');
            await waitForElement('[data-guide="comparison-upload"]', 2000);
            driverObj.moveNext();
          },
        },
      },
      {
        element: '[data-guide="comparison-upload"]',
        onHighlightStarted: () => setActiveTab('comparison'),
        popover: {
          title: '① 여기서 시작 — 대비표 올리기',
          description:
            '원본에 적용할 <b>대비표 엑셀</b>을 여기에 올리세요.<br>' +
            '올리면 바뀔 항목이 표로 나오고, 각 항목에 아래 태그가 붙습니다:' +
            TAG_LEGEND_HTML +
            '<div style="margin-top:8px;">고른 뒤 <b>[선택 항목 적용]</b>을 누르면 원본에 반영됩니다.</div>',
          side: 'bottom',
          align: 'center',
        },
      },
      {
        element: '[data-guide="header-actions"]',
        popover: {
          title: '② 적용 후 — 비교 · 다운로드',
          description:
            '대비표를 적용하면 <b>Diff 비교</b> 탭에서 ' +
            '<b>원본 ↔ 수정본을 비교</b>하고, 칸을 클릭해 <b>직접 수정</b>하거나 검색할 수 있어요.<br>' +
            '마지막에 <b>[수정본 HWP 다운로드]</b>로 결과 파일을 받습니다.<br>' +
            "상단에서 상태 확인 · <b>'원본으로 초기화'</b> · <b>[사용법]</b> 재실행이 가능합니다.",
          side: 'bottom',
          align: 'end',
        },
      },
    ];

    // ── 풀 투어(적용 후): 실제 화면을 단계별로 ──
    const fullSteps: DriveStep[] = [
      {
        element: '.ant-tabs-nav',
        popover: {
          title: '작업 흐름 (3개 탭)',
          description:
            '이 3개 탭으로 작업합니다.<br>' +
            '<b>미리보기</b>(현재 문서) · <b>대비표 일괄 수정</b> · <b>Diff 비교</b>',
          side: 'bottom',
          align: 'center',
          onNextClick: async () => {
            setActiveTab('comparison');
            await waitForElement('[data-guide="comparison-upload"]', 2000);
            driverObj.moveNext();
          },
        },
      },
      {
        element: '[data-guide="comparison-upload"]',
        onHighlightStarted: () => setActiveTab('comparison'),
        popover: {
          title: '대비표(변경 내용) 업로드',
          description:
            '여기에 <b>대비표 엑셀</b>을 올리면, 바뀔 항목 목록과 ' +
            "<b>'구간 처리 현황'</b>이 아래에 나옵니다.<br>" +
            '(구간 현황 옆 ⓘ 에 마우스를 올리면 설명이 보여요.)',
          side: 'bottom',
          align: 'center',
        },
      },
      {
        element: '[data-guide="comparison-result"]',
        onHighlightStarted: () => setActiveTab('comparison'),
        popover: {
          title: '★ 안전 / 주의 — 어떤 걸 적용할까',
          description:
            '바뀔 항목마다 아래 태그가 붙습니다. <b>이 태그를 보고 무엇을 적용할지 판단</b>하세요:' +
            TAG_LEGEND_HTML +
            '<div style="margin-top:8px;">고른 뒤 <b>[선택 항목 적용]</b>을 누르면 원본에 반영됩니다.</div>',
          side: 'bottom',
          align: 'center',
          onNextClick: async () => {
            setActiveTab('diff');
            await waitForElement('[data-guide="diff-area"]', 2000);
            driverObj.moveNext();
          },
        },
      },
      {
        element: '[data-guide="diff-area"]',
        onHighlightStarted: () => setActiveTab('diff'),
        popover: {
          title: 'Diff 비교 / 직접 수정',
          description:
            '여기서 <b>원본 ↔ 수정본을 나란히 비교</b>합니다.<br>' +
            '바뀐 칸은 색으로 표시되고, <b>칸을 클릭해 직접 수정</b>할 수도 있어요.<br>' +
            '상단 🔍 검색으로 특정 단어를 찾을 수 있습니다.',
          side: 'top',
          align: 'center',
          onNextClick: async () => {
            const el = await waitForElement('[data-guide="diff-download"]', 1500);
            if (el) driverObj.moveNext();
            else driverObj.moveTo(5);
          },
        },
      },
      {
        element: '[data-guide="diff-download"]',
        popover: {
          title: '수정본 HWP 다운로드',
          description:
            '마지막으로 <b>[수정본 HWP 다운로드]</b>로 결과 파일을 받습니다.<br>' +
            '(사이트 저장은 자동으로 됩니다.)',
          side: 'top',
          align: 'center',
        },
      },
      {
        element: '[data-guide="header-actions"]',
        popover: {
          title: '상태 확인 · 초기화',
          description:
            "상단에서 현재 상태를 보고, <b>'원본으로 초기화'</b>로 " +
            '처음부터 다시 할 수 있습니다.<br>' +
            '<b>[사용법]</b> 버튼으로 이 안내를 언제든 다시 볼 수 있어요.',
          side: 'bottom',
          align: 'end',
        },
      },
    ];

    driverObj = driver({
      showProgress: true,
      progressText: 'STEP {{current}} / {{total}}',
      nextBtnText: '다음 →',
      prevBtnText: '이전',
      doneBtnText: '완료',
      allowClose: true,
      popoverClass: 'docGuidePopover',
      steps: isAppliedRef.current ? fullSteps : orientationSteps,
      onDestroyed: () => {
        driverRef.current = null;
      },
    });

    driverRef.current = driverObj;
    driverObj.drive();
  }, [setActiveTab]);

  return { startGuide };
}
