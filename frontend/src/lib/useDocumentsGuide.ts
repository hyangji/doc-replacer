'use client';

/**
 * '문서 작업'(/documents) 화면 인앱 가이드 (driver.js).
 * 진입 페이지라 새 사용자에게 "원본 업로드 → 목록에서 열기 → 편집 화면에서 작업" 흐름을 안내한다.
 */
import { useCallback, useEffect, useRef } from 'react';
import { driver, type Driver, type DriveStep } from 'driver.js';
import 'driver.js/dist/driver.css';

// 페이지 이동(문서 작업 → 편집기)을 넘어 가이드를 이어받기 위한 세션 플래그 키.
// 문서 가이드 시작 시 세팅 → 편집기 진입 시 이 값이 있으면 편집기 가이드를 자동으로 이어서 시작.
export const GUIDED_FLOW_KEY = 'docreplacer_guided_flow';

export function useDocumentsGuide() {
  const driverRef = useRef<Driver | null>(null);

  // 페이지 이동(언마운트) 시 진행 중이던 가이드 driver를 정리한다.
  // (가이드가 켜진 채 원본 업로드로 편집기 이동 시, 잔여 오버레이가 편집기 가이드를 막는 문제 방지)
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
    // 가이드 진행 중 표시 → 원본 업로드로 편집기 이동 시 그쪽에서 이어받음
    try {
      window.sessionStorage.setItem(GUIDED_FLOW_KEY, '1');
    } catch {
      // sessionStorage 불가 환경 무시
    }

    const steps: DriveStep[] = [
      // 0. 시작 안내(앵커 없음 = 화면 중앙). 데이터 준비 권장 안내.
      {
        popover: {
          title: '👋 사용 가이드를 시작합니다',
          description:
            '화면을 함께 보며 단계별로 안내해 드려요.<br><br>' +
            '💡 <b>팁</b>: 원본 HWP와 대비표 엑셀을 <b>모두 올려 적용한 뒤</b> 가이드를 보시면, ' +
            '실제로 바뀐 화면으로 <b>더 정확한 안내</b>를 받을 수 있습니다.<br><br>' +
            '지금은 전체 흐름을 가볍게 둘러볼게요.',
          align: 'center',
        },
      },
      {
        element: '[data-guide="upload"]',
        popover: {
          title: '① 원본 문서 업로드',
          description:
            '여기에 <b>원본 HWP/HWPX 파일</b>을 드래그하거나 클릭해서 올리세요.<br>' +
            '올리면 자동으로 <b>편집 화면</b>이 열립니다.',
          side: 'bottom',
          align: 'center',
        },
      },
      {
        element: '[data-guide="doc-list"]',
        popover: {
          title: '② 작업 문서 목록',
          description:
            '올려서 작업한 문서들이 여기 쌓입니다.<br>' +
            '<b>[열기]</b>로 이어서 작업, <b>[삭제]</b>로 정리하세요.<br>' +
            '(다운로드를 안 해도 자동으로 저장됩니다.)',
          side: 'top',
          align: 'center',
        },
      },
      {
        element: '[data-guide="upload"]',
        popover: {
          title: '③ 이제 원본을 올려보세요',
          description:
            '위 영역에 <b>원본 HWP</b>를 올리면 편집 화면으로 넘어가고,<br>' +
            '<b>가이드가 거기서 자동으로 이어집니다</b> (대비표 적용 → 검토 → 다운로드).<br>' +
            '<span style="color:#888;">※ 지금 올리지 않아도, 나중에 올리면 편집 화면에서 안내가 이어져요.</span>',
          side: 'bottom',
          align: 'center',
        },
      },
    ];

    const driverObj = driver({
      showProgress: true,
      progressText: 'STEP {{current}} / {{total}}',
      nextBtnText: '다음 →',
      prevBtnText: '이전',
      doneBtnText: '완료',
      allowClose: true,
      popoverClass: 'docGuidePopover',
      steps,
      onDestroyed: () => {
        driverRef.current = null;
      },
    });

    driverRef.current = driverObj;
    driverObj.drive();
  }, []);

  return { startGuide };
}
