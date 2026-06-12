'use client';

import React, {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Card, Button, Space, Typography, Table, Tag, Spin, message, Modal, Input } from 'antd';
import {
  UpOutlined,
  DownOutlined,
  RollbackOutlined,
  FileWordOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getDocumentHtml, getDocumentCompareHtml, saveBlocks } from '@/lib/api';

const { Title, Text } = Typography;

export interface ChangeRecord {
  key: string;
  index: number;
  line: number;
  type: '수정' | '삭제' | '추가';
  original: string;
  modified: string;
}

interface DiffViewerProps {
  originalContent: string;
  modifiedContent: string;
  originalTitle?: string;
  modifiedTitle?: string;
  documentId?: number;
  originalVersion?: number;
  modifiedVersion?: number;
  onDownloadHwp?: () => void;
  onModifiedTextChange?: (text: string) => void;
  /** 문서 모드에서 인라인 편집(save-blocks)으로 새 버전 저장 성공 시 호출 */
  onDocSaved?: () => void;
  /** 문서 모드 미저장 손편집 존재 여부 변경 시 호출 */
  onDocDirtyChange?: (dirty: boolean) => void;
}

/** 부모가 ref로 접근할 수 있는 핸들 */
export interface DiffViewerHandle {
  /** 문서 모드 미저장 손편집을 save-blocks로 저장(편집 없으면 no-op). 저장 시 true 반환 */
  saveDocBlocks: () => Promise<boolean>;
  /** 현재 문서 모드 미저장 편집 존재 여부 */
  hasDocDirty: () => boolean;
}

const changeTypeColorMap: Record<ChangeRecord['type'], string> = {
  수정: 'orange',
  삭제: 'red',
  추가: 'green',
};

// 문서 모드 변경 칸 토글 버튼용 RollbackOutlined 인라인 SVG(라벨은 CSS ::after로 표시).
const DOC_REVERT_SVG =
  '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" aria-hidden="true">' +
  '<path d="M793 242H366v-74c0-6.7-7.7-10.4-12.9-6.3l-142 112a8 8 0 000 12.6l142 112c5.2 4.1 12.9.4 12.9-6.3v-74h415v470H175c-4.4 0-8 3.6-8 8v60c0 4.4 3.6 8 8 8h618c35.3 0 64-28.7 64-64V306c0-35.3-28.7-64-64-64z"/>' +
  '</svg>';

// 콤마 제외 시 전부 digit(앞에 - 부호 허용)이면 순수 정수 금액으로 간주
function isPureInteger(value: string): boolean {
  const v = value.trim();
  if (!v) return false;
  const stripped = v.replace(/,/g, '');
  return /^-?\d+$/.test(stripped);
}

// '금액(숫자) 칸' 판정: 원본값/수정값이 콤마 포함 숫자이거나 순수 정수면 금액 칸.
function looksLikeAmount(orig: string | null, modified: string | null): boolean {
  const candidates = [orig, modified].filter(
    (v): v is string => v != null && v.trim() !== '',
  );
  if (candidates.length === 0) return false;
  return candidates.some((v) => isPureInteger(v));
}

// 천 단위 콤마 적용. 순수 정수면 정수부 콤마 처리(음수 부호 보존).
// 그 외(단위문자 등 섞임)는 보수적으로 텍스트 내 digit 그룹만 콤마 처리.
function formatAmount(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return value;
  if (isPureInteger(trimmed)) {
    const neg = trimmed.startsWith('-');
    const digits = trimmed.replace(/[-,]/g, '');
    const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '-' : '') + grouped;
  }
  // 혼합 케이스: 3자리 이상 연속 digit 그룹만 콤마 처리(기존 콤마는 먼저 제거)
  return trimmed.replace(/\d[\d,]*/g, (group) => {
    const digits = group.replace(/,/g, '');
    if (!/^\d+$/.test(digits)) return group;
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  });
}

const DiffViewer = forwardRef<DiffViewerHandle, DiffViewerProps>(function DiffViewer({
  originalContent,
  modifiedContent,
  originalTitle = '원본 문서',
  modifiedTitle = '수정된 문서',
  documentId,
  originalVersion = 1,
  modifiedVersion,
  onDownloadHwp,
  onModifiedTextChange,
  onDocSaved,
  onDocDirtyChange,
}: DiffViewerProps, ref) {
  // 변경사항 요약 표에서 선택(하이라이트)된 행 인덱스
  const [currentChangeIndex, setCurrentChangeIndex] = useState(0);

  const [modifiedLines, setModifiedLines] = useState<string[]>(
    modifiedContent.split('\n')
  );

  // 원래 수정본 라인 저장 (수정본으로 되돌리기용)
  const originalModifiedLines = useMemo(
    () => modifiedContent.split('\n'),
    [modifiedContent]
  );

  useEffect(() => {
    setModifiedLines(modifiedContent.split('\n'));
  }, [modifiedContent]);

  const originalLines = useMemo(
    () => originalContent.split('\n'),
    [originalContent]
  );

  const currentModifiedText = useMemo(
    () => modifiedLines.join('\n'),
    [modifiedLines]
  );

  useEffect(() => {
    onModifiedTextChange?.(currentModifiedText);
  }, [currentModifiedText, onModifiedTextChange]);

  // 원래 수정본 기준으로 변경된 줄 목록 (되돌려도 row가 유지됨)
  const changedLines = useMemo(() => {
    const changes: ChangeRecord[] = [];
    const maxLen = Math.max(originalLines.length, originalModifiedLines.length);
    for (let i = 0; i < maxLen; i++) {
      const orig = originalLines[i] ?? '';
      const origMod = originalModifiedLines[i] ?? '';
      if (orig !== origMod) {
        let type: ChangeRecord['type'] = '수정';
        if (i >= originalLines.length) type = '추가';
        else if (i >= originalModifiedLines.length) type = '삭제';
        changes.push({
          key: String(i),
          index: changes.length + 1,
          line: i + 1,
          type,
          original: orig,
          modified: origMod,
        });
      }
    }
    return changes;
  }, [originalLines, originalModifiedLines]);

  // 해당 줄이 원본으로 되돌려진 상태인지 확인
  const isRevertedToOriginal = useCallback((lineIndex: number) => {
    const orig = originalLines[lineIndex] ?? '';
    const origMod = originalModifiedLines[lineIndex] ?? '';
    const current = modifiedLines[lineIndex] ?? '';
    // 원래 수정본과 원본이 다르고, 현재 원본과 같으면 되돌려진 상태
    return orig !== origMod && current === orig;
  }, [originalLines, originalModifiedLines, modifiedLines]);

  // --- 문서 모드: 좌/우 HTML 패널 스크롤 동기화 ---
  const docOriginalRef = useRef<HTMLDivElement>(null);
  const docModifiedRef = useRef<HTMLDivElement>(null);
  // 프로그래밍적 스크롤 중 상대 onScroll을 무시해 무한 루프(떨림) 방지
  const isSyncingDocScrollRef = useRef(false);
  // 수정본 셀 클릭 시 강조한 원본 대응 셀(한 번에 하나만 유지)
  const linkedOriginalCellRef = useRef<HTMLElement | null>(null);

  const syncDocScroll = useCallback((source: 'original' | 'modified') => {
    if (isSyncingDocScrollRef.current) return;
    const src = source === 'original' ? docOriginalRef.current : docModifiedRef.current;
    const dst = source === 'original' ? docModifiedRef.current : docOriginalRef.current;
    if (!src || !dst) return;
    isSyncingDocScrollRef.current = true;
    dst.scrollTop = src.scrollTop;
    dst.scrollLeft = src.scrollLeft;
    // 다음 프레임에 가드 해제 (대입으로 발생한 상대 스크롤 이벤트 소비 후)
    requestAnimationFrame(() => {
      isSyncingDocScrollRef.current = false;
    });
  }, []);

  // 이전에 강조한 원본 대응 셀의 강조를 해제(한 번에 하나만)
  const clearLinkedOriginalCell = useCallback(() => {
    const prev = linkedOriginalCellRef.current;
    if (prev) {
      prev.classList.remove('doc-cell-linked');
      linkedOriginalCellRef.current = null;
    }
  }, []);

  // 수정본(우측) 셀(data-eid) 클릭 → 원본(좌측) 패널의 대응 셀을 검은 테두리로 강조 + 스크롤.
  // 매칭 우선순위: (1) data-eid 동일값  →  (2) 폴백: 문서 순서 위치 인덱스.
  const highlightLinkedOriginalCell = useCallback((modCell: HTMLElement) => {
    const origRoot = docOriginalRef.current;
    if (!origRoot) return;

    let target: HTMLElement | null = null;

    // (1) data-eid 기반: 원본 패널에 data-eid가 하나라도 있으면 사용
    const eid = modCell.getAttribute('data-eid');
    const origHasEid = origRoot.querySelector('[data-eid]') != null;
    if (eid && origHasEid) {
      target = origRoot.querySelector<HTMLElement>(
        `[data-eid="${CSS.escape(eid)}"]`,
      );
    }

    // (2) 폴백: 위치 인덱스 매칭(원본에 data-eid가 없을 때)
    if (!target && !origHasEid) {
      const modRoot = docModifiedRef.current;
      if (modRoot) {
        const modCells = Array.from(
          modRoot.querySelectorAll<HTMLElement>('[data-eid]'),
        );
        const idx = modCells.indexOf(modCell);
        if (idx !== -1) {
          // 원본: 표 셀(td/th) + 표 밖 문단(p) 을 문서 순서대로
          const origCells = Array.from(
            origRoot.querySelectorAll<HTMLElement>('td, th, p'),
          ).filter(
            (el) => el.tagName !== 'P' || !el.closest('td, th'),
          );
          // 개수 불일치면 안전하게 강조 생략
          if (origCells.length === modCells.length) {
            target = origCells[idx] ?? null;
          }
        }
      }
    }

    clearLinkedOriginalCell();
    if (!target) return;
    target.classList.add('doc-cell-linked');
    linkedOriginalCellRef.current = target;
    // 원본 패널 내부에서만 스크롤(좌우 동기화가 자연스럽게 따라옴)
    target.scrollIntoView({ block: 'center' });
  }, [clearLinkedOriginalCell]);

  // --- 문서 모드: 표 보존 HTML 렌더 ---
  const [originalHtml, setOriginalHtml] = useState<string | null>(null);
  const [modifiedHtml, setModifiedHtml] = useState<string | null>(null);
  const [htmlLoading, setHtmlLoading] = useState(false);
  const [htmlError, setHtmlError] = useState<string | null>(null);
  const [docSaving, setDocSaving] = useState(false);
  // 문서 모드 수정본 패널(data-eid)의 eid별 baseline(저장 기준) 텍스트
  const docBaselineRef = useRef<Map<number, string>>(new Map());

  // --- 문서 모드: 검색 ---
  const [docSearch, setDocSearch] = useState('');
  const [docMatchCount, setDocMatchCount] = useState(0);
  const [docMatchIndex, setDocMatchIndex] = useState(0); // 0-based 현재 매치
  // CSS Custom Highlight API 지원 여부 (비파괴적 하이라이트)
  const supportsHighlightApi =
    typeof CSS !== 'undefined' &&
    typeof Highlight !== 'undefined' &&
    typeof CSS.highlights !== 'undefined';
  // 현재 검색 매치들의 Range 목록(좌/우 패널 통합, 순서대로)
  const docMatchRangesRef = useRef<Range[]>([]);
  // 현재 강조 중인 검색 매치 엘리먼트(한 번에 하나만, 다음 매치로 갈 때 해제)
  const currentMatchElRef = useRef<HTMLElement | null>(null);
  // 강조 적용을 다음 프레임으로 미루기 위한 rAF id(리렌더의 innerHTML 재적용 후 적용)
  const searchRafRef = useRef<number>(0);

  // --- 문서 모드: 변경 칸 점프 ---
  const [docChangeCount, setDocChangeCount] = useState(0);
  const docChangeIndexRef = useRef(0);
  // 같은 요청 재호출 방지용 캐시
  //  - 단일 버전 렌더: key = `v${version}`, value = html
  //  - 비교(하이라이트) 렌더: key = `cmp${base}|${target}`, value = {original_html, modified_html}
  const htmlCacheRef = useRef<Map<string, string>>(new Map());
  const compareCacheRef = useRef<
    Map<string, { original_html: string; modified_html: string }>
  >(new Map());

  useEffect(() => {
    if (documentId == null) return;

    let cancelled = false;

    const fetchSingle = async (version: number): Promise<string> => {
      const key = `v${version}`;
      const cached = htmlCacheRef.current.get(key);
      if (cached != null) return cached;
      const html = await getDocumentHtml(documentId, version);
      htmlCacheRef.current.set(key, html);
      return html;
    };

    const fetchCompare = async (
      base: number,
      target: number,
    ): Promise<{ original_html: string; modified_html: string }> => {
      // editable=true: 수정본(modified_html)에만 data-eid / data-orig 부여
      const key = `cmp${base}|${target}|edit`;
      const cached = compareCacheRef.current.get(key);
      if (cached != null) return cached;
      const result = await getDocumentCompareHtml(documentId, base, target, true);
      compareCacheRef.current.set(key, result);
      return result;
    };

    const load = async () => {
      setHtmlLoading(true);
      setHtmlError(null);
      try {
        if (modifiedVersion != null) {
          // 변경 있음: 비교 API로 하이라이트 포함 HTML 받기
          const { original_html, modified_html } = await fetchCompare(
            originalVersion,
            modifiedVersion,
          );
          if (cancelled) return;
          setOriginalHtml(original_html);
          setModifiedHtml(modified_html);
        } else {
          // 변경 없음: 단일 버전 렌더(하이라이트 없음)
          const html = await fetchSingle(originalVersion);
          if (cancelled) return;
          setOriginalHtml(html);
          setModifiedHtml(html);
        }
      } catch {
        if (cancelled) return;
        setHtmlError('문서를 불러오지 못했습니다.');
      } finally {
        if (!cancelled) setHtmlLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [documentId, originalVersion, modifiedVersion]);

  // --- 문서 모드: 수정본 패널(data-eid) 인라인 편집 ---

  // host 셀의 텍스트만 바꾸고, 주입된 토글 버튼 span은 보존한다.
  // (host.textContent = ... 로 통째 교체하면 버튼 span이 사라지므로 사용 금지)
  const setHostText = useCallback((host: HTMLElement, text: string) => {
    const btn = host.querySelector<HTMLElement>('[data-revert-eid]');
    if (btn) btn.remove();
    host.textContent = text;
    if (btn) host.appendChild(btn);
  }, []);

  // 버튼 span의 라벨/타이틀을 현재 토글 상태에 맞게 갱신.
  // 라벨 텍스트는 CSS ::after(content)로 표시하므로 버튼 span 자체는 빈 상태 유지
  // → host.textContent 오염 없음(baseline/save-blocks/검색 로직 무영향).
  const updateToggleBtn = useCallback((host: HTMLElement) => {
    const btn = host.querySelector<HTMLElement>('[data-revert-eid]');
    if (!btn) return;
    const modified = host.getAttribute('data-modified');
    // 버튼 SVG/라벨은 textContent에 기여하지 않으므로 host.textContent == 셀 글자
    const current = host.textContent ?? '';
    // 현재 수정값을 보고 있으면 → 버튼은 "원본으로 되돌리기"
    const showingModified = modified != null && current === modified;
    if (showingModified) {
      btn.setAttribute('title', '원본 값으로 되돌리기');
      btn.setAttribute('data-toggle-state', 'modified');
    } else {
      btn.setAttribute('title', '수정값으로 되돌리기');
      btn.setAttribute('data-toggle-state', 'other');
    }
  }, []);

  // 변경 셀에 절대배치한 토글 버튼(원본 ↔ 수정값) 클릭 처리(이벤트 위임)
  // 토글 버튼이 아닌 셀 본문 클릭이면 원본 패널의 대응 셀을 강조한다.
  const handleDocModifiedClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null;
    if (!target) return;
    const revertBtn = target.closest<HTMLElement>('[data-revert-eid]');
    if (!revertBtn) {
      // 셀 본문 클릭(포커스): 원본 대응 셀 강조
      const cell = target.closest<HTMLElement>('[data-eid]');
      if (cell) highlightLinkedOriginalCell(cell);
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    const host = revertBtn.closest<HTMLElement>('[data-eid]');
    if (!host) return;
    const orig = host.getAttribute('data-orig');
    const modified = host.getAttribute('data-modified');
    const current = host.textContent ?? '';
    // 수정값을 보고 있으면 → 원본으로. 그 외(원본/손편집)면 → 수정값으로.
    if (modified != null && current === modified) {
      if (orig != null) setHostText(host, orig);
    } else if (modified != null) {
      setHostText(host, modified);
    } else if (orig != null) {
      setHostText(host, orig);
    }
    updateToggleBtn(host);
    recomputeDocDirty();
  }, [setHostText, updateToggleBtn, highlightLinkedOriginalCell]); // eslint-disable-line react-hooks/exhaustive-deps

  // 문서 모드 미저장 편집 존재 여부를 재계산해 부모에 알림
  const recomputeDocDirty = useCallback(() => {
    const container = docModifiedRef.current;
    if (!container) return;
    const baseline = docBaselineRef.current;
    const nodes = container.querySelectorAll<HTMLElement>('[data-eid]');
    let dirty = false;
    nodes.forEach((el) => {
      if (dirty) return;
      const eid = Number(el.dataset.eid);
      if (Number.isNaN(eid)) return;
      const current = el.textContent ?? '';
      const original = baseline.get(eid) ?? '';
      if (current !== original) dirty = true;
    });
    onDocDirtyChange?.(dirty);
  }, [onDocDirtyChange]);

  // 셀 blur: 금액 칸이면 천 단위 콤마 자동 적용(버튼 span 보존) + dirty 재계산
  const handleDocBlur = useCallback((e: React.FocusEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null;
    if (!target || !(target instanceof HTMLElement)) return;
    const host = target.closest<HTMLElement>('[data-eid]');
    if (!host) return;
    const orig = host.getAttribute('data-orig');
    const modified = host.getAttribute('data-modified');
    if (looksLikeAmount(orig, modified)) {
      const current = host.textContent ?? '';
      const formatted = formatAmount(current);
      if (formatted !== current) {
        setHostText(host, formatted);
        if (host.hasAttribute('data-orig')) updateToggleBtn(host);
      }
    }
    recomputeDocDirty();
  }, [setHostText, updateToggleBtn, recomputeDocDirty]);

  // --- 문서 모드 검색: CSS Custom Highlight API 기반 비파괴 하이라이트 ---

  // 패널 내 모든 텍스트 노드를 순서대로 모은다(편집 버튼 SVG 등은 텍스트 없음).
  const collectTextNodes = useCallback((root: HTMLElement): Text[] => {
    const out: Text[] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        // 주입한 토글 버튼(span[data-revert-eid]) 내부 텍스트는 제외
        const parent = (node as Text).parentElement;
        if (parent && parent.closest('[data-revert-eid]')) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n = walker.nextNode();
    while (n) {
      out.push(n as Text);
      n = walker.nextNode();
    }
    return out;
  }, []);

  // 한 패널에서 검색어 매치 Range들을 만든다.
  const findRangesInPanel = useCallback(
    (root: HTMLElement | null, query: string): Range[] => {
      if (!root || !query) return [];
      const lower = query.toLowerCase();
      const ranges: Range[] = [];
      const textNodes = collectTextNodes(root);
      for (const node of textNodes) {
        const text = node.textContent ?? '';
        if (!text) continue;
        const hay = text.toLowerCase();
        let from = 0;
        let idx = hay.indexOf(lower, from);
        while (idx !== -1) {
          const range = document.createRange();
          range.setStart(node, idx);
          range.setEnd(node, idx + query.length);
          ranges.push(range);
          from = idx + query.length;
          idx = hay.indexOf(lower, from);
        }
      }
      return ranges;
    },
    [collectTextNodes],
  );

  // 현재 강조용으로 감싼 <span.doc-search-hit>을 풀어 DOM을 원상복구한다.
  // (span은 텍스트만 품으므로 풀면 textContent 불변 → 저장/검색 기준 영향 없음)
  const unwrapSearchMark = useCallback(() => {
    const span = currentMatchElRef.current;
    currentMatchElRef.current = null;
    if (!span || !span.parentNode) return;
    const parent = span.parentNode;
    while (span.firstChild) parent.insertBefore(span.firstChild, span);
    parent.removeChild(span);
    parent.normalize(); // 쪼개졌던 텍스트 노드 병합
  }, []);

  // 검색 매치 강조: "현재 매치 글자만" <span.doc-search-hit>로 감싸 정확히 색칠 + 스크롤.
  // 블록 전체 색칠 방지. 매번 새로 찾아 한 곳만 감싸므로 Range 무효화 문제 없음.
  const applyMatch = useCallback(
    (query: string, rawIdx: number) => {
      if (searchRafRef.current) {
        cancelAnimationFrame(searchRafRef.current);
        searchRafRef.current = 0;
      }
      const q = query.trim();
      if (!q) {
        unwrapSearchMark();
        setDocMatchCount(0);
        setDocMatchIndex(0);
        return;
      }
      const all = [
        ...findRangesInPanel(docOriginalRef.current, q),
        ...findRangesInPanel(docModifiedRef.current, q),
      ];
      setDocMatchCount(all.length);
      if (all.length === 0) {
        unwrapSearchMark();
        setDocMatchIndex(0);
        return;
      }
      const idx = ((rawIdx % all.length) + all.length) % all.length;
      setDocMatchIndex(idx);
      // 강조 DOM 변경은 "다음 프레임"에 적용한다. setDocMatchCount/Index로 인한 리렌더에서
      // React가 패널 innerHTML을 다시 그리며 우리가 넣은 span을 지우는데, rAF는 그 커밋 "후"에
      // 실행되므로 여기서 감싼 span은 살아남는다. (재렌더 후 DOM 기준 다시 찾아 감쌈)
      searchRafRef.current = requestAnimationFrame(() => {
        searchRafRef.current = 0;
        unwrapSearchMark();
        const fresh = [
          ...findRangesInPanel(docOriginalRef.current, q),
          ...findRangesInPanel(docModifiedRef.current, q),
        ];
        const r = fresh[idx] ?? fresh[fresh.length - 1];
        if (!r) return;
        try {
          const mark = document.createElement('span');
          mark.className = 'doc-search-hit';
          r.surroundContents(mark);
          currentMatchElRef.current = mark;
          mark.scrollIntoView({ block: 'center', inline: 'center' });
        } catch {
          (r.startContainer.parentElement as HTMLElement | null)?.scrollIntoView({
            block: 'center',
          });
        }
      });
    },
    [findRangesInPanel, unwrapSearchMark],
  );

  const clearDocHighlights = useCallback(() => {
    unwrapSearchMark();
    docMatchRangesRef.current = [];
  }, [unwrapSearchMark]);

  // 검색 실행(입력 시): query 기준으로 찾아 첫 매치 강조
  const runDocSearch = useCallback(
    (query: string, focusIndex = 0) => {
      applyMatch(query, focusIndex);
    },
    [applyMatch],
  );

  const navigateDocMatch = useCallback(
    (direction: 'prev' | 'next') => {
      if (docMatchCount === 0) return;
      const next = direction === 'next' ? docMatchIndex + 1 : docMatchIndex - 1;
      applyMatch(docSearch, next); // applyMatch 내부에서 wrap-around 처리
    },
    [docMatchCount, docMatchIndex, docSearch, applyMatch],
  );

  // 변경 칸(data-orig 보유) 점프
  const navigateDocChange = useCallback(
    (direction: 'prev' | 'next') => {
      const container = docModifiedRef.current;
      if (!container) return;
      const nodes = Array.from(
        container.querySelectorAll<HTMLElement>('[data-eid][data-orig]'),
      );
      if (nodes.length === 0) return;
      let idx = docChangeIndexRef.current;
      idx =
        direction === 'next'
          ? (idx + 1) % nodes.length
          : (idx - 1 + nodes.length) % nodes.length;
      docChangeIndexRef.current = idx;
      nodes[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
      // 잠깐 강조
      const el = nodes[idx];
      const prevOutline = el.style.outline;
      el.style.outline = '2px solid #faad14';
      window.setTimeout(() => {
        el.style.outline = prevOutline;
      }, 1200);
    },
    [],
  );

  // 셀 안에서 Enter(행/줄 생성) 차단
  const handleDocKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null;
    if (!target || !(target instanceof HTMLElement)) return;
    if (!target.closest('[data-eid]')) return;
    if (e.key === 'Enter') {
      e.preventDefault();
    }
  }, []);

  // 붙여넣기: plain text만(서식/HTML 차단, 개행→공백)
  const handleDocPaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement | null;
    if (!target || !(target instanceof HTMLElement)) return;
    if (!target.closest('[data-eid]')) return;
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain').replace(/\r?\n/g, ' ');
    if (text) {
      document.execCommand('insertText', false, text);
    }
  }, []);

  // 수정본 HTML 렌더 후: data-eid 요소를 편집 가능하게 만들고 baseline 기록 + 변경 셀에 토글 버튼 주입.
  // 실제 주입 로직(컨테이너 대상). 주입 성공(=처리한 data-eid 수) 여부를 반환.
  const injectEditableCells = useCallback((container: HTMLElement): number => {
    // 편집 속성(contenteditable)·토글 버튼·data-modified 는 이미 processedModifiedHtml(HTML 문자열)에
    // 선반영되어 렌더되므로, 여기서는 DOM을 변형하지 않고 baseline 기록 + 부가정보만 갱신한다.
    // (JS로 나중에 DOM을 건드리면 React의 innerHTML 재적용에 덮어써지는 문제를 원천 회피)
    const nodes = container.querySelectorAll<HTMLElement>('[data-eid]');
    const baseline = new Map<number, string>();
    nodes.forEach((el) => {
      const eid = Number(el.dataset.eid);
      if (Number.isNaN(eid)) return;
      // 버튼 span(SVG)은 텍스트가 없어 textContent = 셀 글자. baseline/save-blocks 비교 정확.
      baseline.set(eid, el.textContent ?? '');
    });
    docBaselineRef.current = baseline;
    onDocDirtyChange?.(false);

    // 변경 칸 수 갱신 + 검색 초기화(새 HTML 렌더로 기존 Range가 무효화되므로)
    const changeNodes = container.querySelectorAll('[data-eid][data-orig]');
    setDocChangeCount(changeNodes.length);
    docChangeIndexRef.current = 0;
    // 새 HTML 렌더로 기존 강조 셀 참조가 무효화되므로 정리
    clearLinkedOriginalCell();
    clearDocHighlights();
    setDocMatchCount(0);
    setDocMatchIndex(0);
    if (docSearch.trim()) {
      // 새 DOM에서 검색어 재적용
      runDocSearch(docSearch, 0);
    }
    return nodes.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onDocDirtyChange, clearDocHighlights]);

  // 수정본 HTML 문자열에 편집 속성/토글 버튼/data-modified 를 "선반영"한 결과.
  // JS로 DOM을 나중에 건드리지 않고 처음부터 HTML에 포함시켜 렌더하므로,
  // React가 innerHTML을 다시 그려도 편집 기능이 사라지지 않는다.
  const processedModifiedHtml = useMemo(() => {
    if (!modifiedHtml) return '';
    if (typeof window === 'undefined' || typeof DOMParser === 'undefined') return modifiedHtml;
    const parsed = new DOMParser().parseFromString(
      `<body><div id="__docroot">${modifiedHtml}</div></body>`,
      'text/html',
    );
    const root = parsed.getElementById('__docroot');
    if (!root) return modifiedHtml;
    root.querySelectorAll('[data-eid]').forEach((el) => {
      const eid = el.getAttribute('data-eid');
      if (!eid) return;
      el.setAttribute('contenteditable', 'true');
      el.setAttribute('spellcheck', 'false');
      el.setAttribute('data-editable-cell', 'true');
      // 변경 칸(data-orig 보유)에 수정값 스냅샷(data-modified) + 토글 버튼 선반영
      if (el.hasAttribute('data-orig')) {
        const text = el.textContent ?? ''; // 버튼 추가 전 = 순수 셀 글자
        el.setAttribute('data-modified', text);
        const style = el.getAttribute('style') ?? '';
        if (!/position\s*:/i.test(style)) {
          el.setAttribute('style', (style ? style.replace(/\s*;?\s*$/, '; ') : '') + 'position: relative');
        }
        const btn = parsed.createElement('span');
        btn.setAttribute('data-revert-eid', eid);
        btn.setAttribute('contenteditable', 'false');
        btn.setAttribute('data-toggle-state', 'modified'); // 초기: 수정값 표시중 → 누르면 원본
        btn.setAttribute('title', '원본 값으로 되돌리기');
        btn.className = 'doc-revert-btn';
        btn.innerHTML = DOC_REVERT_SVG;
        el.appendChild(btn);
      }
    });
    return root.innerHTML;
  }, [modifiedHtml]);

  // 수정본 패널 div가 마운트되는 "순간"(ref 콜백)에 즉시 편집 기능을 주입한다.
  // ref 콜백은 React가 dangerouslySetInnerHTML로 innerHTML을 채운 직후에 호출되므로,
  // effect 타이밍(페인트 전/후, in-place 갱신)에 의존하지 않아 주입 누락이 원천 차단된다.
  // → contentEditable(수동 수정) + 토글 버튼이 문서 탭 첫 진입부터 안정적으로 적용됨.
  // key={modifiedHtml}로 HTML이 바뀌면 div가 새로 마운트 → 매번 깨끗한 DOM에 재주입.
  const docModifiedRefCallback = useCallback(
    (node: HTMLDivElement | null) => {
      docModifiedRef.current = node;
      if (!node) return;
      const count = injectEditableCells(node);
      // 극히 드물게 innerHTML 커밋이 늦어 data-eid가 0개면 다음 프레임 재시도
      if (count === 0 && node.innerHTML.trim() !== '') {
        requestAnimationFrame(() => {
          if (docModifiedRef.current) injectEditableCells(docModifiedRef.current);
        });
      }
    },
    [injectEditableCells],
  );

  // 문서 모드 저장: baseline과 달라진 data-eid만 모아 save-blocks 호출 → 새 버전
  // silent=true 이면 안내 모달을 띄우지 않음(다운로드 직전 자동저장 등 내부 호출용).
  // 반환값: 실제로 저장을 수행했으면 true, 변경 없음/실패면 false.
  const saveDocBlocksInternal = useCallback(async (silent = false): Promise<boolean> => {
    if (documentId == null) return false;
    const container = docModifiedRef.current;
    if (!container) return false;

    const baseline = docBaselineRef.current;
    const nodes = container.querySelectorAll<HTMLElement>('[data-eid]');
    const edits: { eid: number; text: string }[] = [];
    nodes.forEach((el) => {
      const eid = Number(el.dataset.eid);
      if (Number.isNaN(eid)) return;
      const current = el.textContent ?? '';
      const original = baseline.get(eid) ?? '';
      if (current !== original) {
        edits.push({ eid, text: current });
      }
    });

    if (edits.length === 0) {
      if (!silent) message.info('변경된 내용이 없습니다.');
      onDocDirtyChange?.(false);
      return false;
    }

    setDocSaving(true);
    try {
      await saveBlocks(documentId, edits);
      edits.forEach((e) => baseline.set(e.eid, e.text));
      onDocDirtyChange?.(false);
      // 새 버전 기준으로 비교 새로고침 위해 캐시 무효화
      compareCacheRef.current.clear();
      htmlCacheRef.current.clear();
      onDocSaved?.();
      if (!silent) {
        Modal.success({
          title: '저장 완료',
          content:
            '서버에 새 버전으로 저장되었습니다. 한글(HWP) 파일이 필요하면 아래 "수정본 HWP 다운로드"를 누르세요. (사이트 저장과 파일 다운로드는 별개입니다.)',
          okText: '확인',
        });
      }
      return true;
    } catch {
      // 에러 메시지는 인터셉터에서 표시됨
      return false;
    } finally {
      setDocSaving(false);
    }
  }, [documentId, onDocSaved, onDocDirtyChange]);

  // 부모(다운로드 핸들러 등)가 ref로 호출할 수 있는 핸들 노출
  useImperativeHandle(ref, () => ({
    saveDocBlocks: () => saveDocBlocksInternal(true),
    hasDocDirty: () => {
      const container = docModifiedRef.current;
      if (!container) return false;
      const baseline = docBaselineRef.current;
      const nodes = container.querySelectorAll<HTMLElement>('[data-eid]');
      for (const el of nodes) {
        const eid = Number((el as HTMLElement).dataset.eid);
        if (Number.isNaN(eid)) continue;
        const current = el.textContent ?? '';
        const original = baseline.get(eid) ?? '';
        if (current !== original) return true;
      }
      return false;
    },
  }), [saveDocBlocksInternal]);

  const changeColumns: ColumnsType<ChangeRecord> = [
    { title: '#', dataIndex: 'index', key: 'index', width: 50 },
    { title: '위치', dataIndex: 'line', key: 'line', width: 80, render: (line: number) => `${line}줄` },
    {
      title: '유형', dataIndex: 'type', key: 'type', width: 80,
      render: (type: ChangeRecord['type']) => <Tag color={changeTypeColorMap[type]}>{type}</Tag>,
    },
    {
      title: '이전 값', dataIndex: 'original', key: 'original', ellipsis: true,
      render: (text: string) => <Text type={text ? undefined : 'secondary'}>{text || '-'}</Text>,
    },
    {
      title: '새 값', dataIndex: 'modified', key: 'modified', ellipsis: true,
      render: (text: string) => <Text type={text ? undefined : 'secondary'}>{text || '-'}</Text>,
    },
    // 되돌리기는 문서 화면에서 해당 셀에 마우스를 올려 '원본↔수정값' 토글 버튼으로 수행한다.
    // (요약표의 줄 단위 되돌리기는 표 보존 문서 화면에 반영되지 않아 제거 — 읽기 전용 목록)
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 문서 모드: 표 보존 HTML 좌우 렌더 (문서 모드 전용 — 항상 렌더) */}
      <>
          {htmlLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 48 }}>
              <Spin />
              <Text type="secondary">문서를 불러오는 중...</Text>
            </div>
          )}
          {!htmlLoading && htmlError && (
            <Card size="small">
              <Text type="danger">{htmlError}</Text>
            </Card>
          )}
          {!htmlLoading && !htmlError && (
            <>
            {/* 문서 모드 검색/네비게이션 툴바 */}
            <Card size="small" style={{ marginBottom: 2 }} styles={{ body: { padding: '8px 12px' } }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
                <Space size={6}>
                  <Text type="secondary" style={{ fontSize: 12 }}>🔍 검색:</Text>
                  <Input
                    allowClear
                    size="small"
                    style={{ width: 200 }}
                    placeholder="문서에서 텍스트 찾기"
                    value={docSearch}
                    onChange={(e) => {
                      const v = e.target.value;
                      setDocSearch(v);
                      runDocSearch(v, 0);
                    }}
                    onPressEnter={() => navigateDocMatch('next')}
                  />
                  <Button
                    size="small"
                    icon={<UpOutlined />}
                    disabled={docMatchCount === 0}
                    onClick={() => navigateDocMatch('prev')}
                  >
                    이전
                  </Button>
                  <Button
                    size="small"
                    icon={<DownOutlined />}
                    disabled={docMatchCount === 0}
                    onClick={() => navigateDocMatch('next')}
                  >
                    다음
                  </Button>
                  {docSearch.trim() && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {docMatchCount > 0 ? `${docMatchIndex + 1}/${docMatchCount}` : '검색 결과 없음'}
                    </Text>
                  )}
                </Space>
              </div>
            </Card>
            <div style={{ display: 'flex', gap: 2, height: 'calc(100vh - 420px)', minHeight: 360 }}>
              {/* 좌측: 원본 HTML */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{
                  padding: '8px 12px',
                  background: '#f5f5f5',
                  borderBottom: '1px solid #d9d9d9',
                  fontWeight: 600,
                  fontSize: 13,
                }}>
                  {originalTitle}
                </div>
                <div
                  ref={docOriginalRef}
                  onScroll={() => syncDocScroll('original')}
                  className="doc-html-render doc-original"
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    border: '1px solid #d9d9d9',
                    borderTop: 0,
                    background: '#fafafa',
                    padding: 12,
                    fontSize: 13,
                  }}
                  dangerouslySetInnerHTML={{ __html: originalHtml ?? '' }}
                />
              </div>

              {/* 우측: 수정본 HTML (편집 가능) */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '6px 8px 6px 12px',
                  background: '#e6f4ff',
                  borderBottom: '1px solid #91caff',
                  fontWeight: 600,
                  fontSize: 13,
                  color: '#1677ff',
                }}>
                  <span>{modifiedTitle} (클릭해 수정)</span>
                  <Space size={4}>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>변경 칸:</Text>
                    <Button
                      size="small"
                      icon={<UpOutlined />}
                      disabled={docChangeCount === 0}
                      onClick={() => navigateDocChange('prev')}
                    >
                      이전
                    </Button>
                    <Button
                      size="small"
                      icon={<DownOutlined />}
                      disabled={docChangeCount === 0}
                      onClick={() => navigateDocChange('next')}
                    >
                      다음
                    </Button>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>{docChangeCount}개</Text>
                  </Space>
                </div>
                <div
                  key={processedModifiedHtml || 'empty'}
                  ref={docModifiedRefCallback}
                  onScroll={() => syncDocScroll('modified')}
                  onClick={handleDocModifiedClick}
                  onKeyDown={handleDocKeyDown}
                  onPaste={handleDocPaste}
                  onBlur={handleDocBlur}
                  onInput={recomputeDocDirty}
                  className="doc-html-render doc-modified doc-modified-editable"
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    border: '1px solid #91caff',
                    borderTop: 0,
                    background: '#fff',
                    padding: 12,
                    fontSize: 13,
                  }}
                  dangerouslySetInnerHTML={{ __html: processedModifiedHtml }}
                />
              </div>
            </div>
            </>
          )}
        </>

      {/* 문서 모드 표 스타일 */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
            .doc-html-render table {
              border-collapse: collapse;
              max-width: 100%;
            }
            .doc-html-render table,
            .doc-html-render td,
            .doc-html-render th {
              border: 1px solid #d9d9d9;
            }
            .doc-html-render td,
            .doc-html-render th {
              padding: 3px 6px;
              font-size: 13px;
              vertical-align: top;
            }
            .doc-html-render p {
              margin: 0 0 6px;
            }
            /* 변경 하이라이트: 셀(td) 배경 + 인라인 단어(span) 배경 모두 적용 */
            .doc-original .hwp-changed {
              background: #ffd6d6;
              color: #cf1322;
            }
            /* 수정본 셀 클릭 시 원본 패널의 대응 셀 강조(검은 테두리, hwp-changed 색강조와 구분) */
            .doc-original .doc-cell-linked {
              outline: 2px solid #000;
              outline-offset: -1px;
              background: #fffbe6;
            }
            .doc-modified .hwp-changed {
              background: #b7eb8f;
              color: #135200;
              font-weight: 700;
            }
            /* 수정본 편집 affordance */
            .doc-modified-editable [data-eid] {
              outline: none;
              cursor: text;
              transition: background 0.12s ease, box-shadow 0.12s ease;
              border-radius: 2px;
            }
            .doc-modified-editable [data-eid]:hover {
              background: #f0f7ff;
            }
            .doc-modified-editable [data-eid]:focus {
              background: #e6f4ff;
              box-shadow: inset 0 0 0 2px #4096ff;
            }
            /* 변경 셀에 주입한 토글 버튼: 평소 숨김(숫자 가리지 않음) → 셀 hover/focus 시에만 노출.
               아이콘만(라벨 없음), 색/방향으로 상태 구분. */
            .doc-modified-editable .doc-revert-btn {
              position: absolute;
              top: 1px;
              right: 1px;
              display: none;
              align-items: center;
              justify-content: center;
              width: 16px;
              height: 16px;
              line-height: 1;
              color: #ff4d4f;
              background: #fff;
              border: 1px solid #ffccc7;
              border-radius: 3px;
              cursor: pointer;
              user-select: none;
              z-index: 2;
              opacity: 0.95;
              box-shadow: 0 0 0 2px #fff;
            }
            .doc-modified-editable [data-eid]:hover > .doc-revert-btn,
            .doc-modified-editable [data-eid]:focus > .doc-revert-btn,
            .doc-modified-editable [data-eid]:focus-within > .doc-revert-btn {
              display: inline-flex;
            }
            .doc-modified-editable .doc-revert-btn:hover {
              opacity: 1;
              background: #fff1f0;
            }
            .doc-modified-editable .doc-revert-btn svg {
              width: 11px;
              height: 11px;
            }
            /* 토글 상태별 색/방향 구분(아이콘만) */
            /* 수정값 보는 중 → 누르면 원본으로(빨강) */
            .doc-modified-editable .doc-revert-btn[data-toggle-state="modified"] {
              color: #ff4d4f;
              border-color: #ffccc7;
              background: #fff;
            }
            .doc-modified-editable .doc-revert-btn[data-toggle-state="modified"]:hover {
              background: #fff1f0;
            }
            /* 원본/손편집 보는 중 → 누르면 수정값으로(파랑, svg 좌우반전) */
            .doc-modified-editable .doc-revert-btn[data-toggle-state="other"] {
              color: #1677ff;
              border-color: #91caff;
              background: #fff;
            }
            .doc-modified-editable .doc-revert-btn[data-toggle-state="other"]:hover {
              background: #e6f4ff;
            }
            .doc-modified-editable .doc-revert-btn[data-toggle-state="other"] svg {
              transform: scaleX(-1);
            }
            /* 문서 모드 검색 현재 매치 강조(매치된 글자만 span으로 감싸 색칠) */
            .doc-search-hit {
              background: #ffe066 !important;
              color: #000 !important;
              font-weight: 700 !important;
              padding: 1px 2px;
              border-radius: 3px;
              box-shadow: 0 0 0 3px #fa541c, 0 0 10px 3px rgba(250, 84, 28, 0.55);
              scroll-margin: 120px;
              animation: docSearchPulse 0.6s ease-in-out 3;
            }
            @keyframes docSearchPulse {
              0%, 100% { background: #ffe066; box-shadow: 0 0 0 3px #fa541c, 0 0 10px 3px rgba(250,84,28,0.55); }
              50% { background: #ff7a45; box-shadow: 0 0 0 4px #d4380d, 0 0 16px 5px rgba(212,56,13,0.8); }
            }
          `,
        }}
      />

      {/* 변경사항 요약 테이블 */}
      {changedLines.length > 0 && (
        <Card
          size="small"
          title={<Title level={5} style={{ margin: 0 }}>변경사항 요약 ({changedLines.length}건)</Title>}
        >
          <Table<ChangeRecord>
            columns={changeColumns}
            dataSource={changedLines}
            pagination={false}
            size="small"
            scroll={{ y: 300 }}
            rowClassName={(record, index) => {
              const classes: string[] = [];
              if (index === currentChangeIndex) classes.push('ant-table-row-selected');
              if (isRevertedToOriginal(record.line - 1)) classes.push('ant-table-row-reverted');
              return classes.join(' ');
            }}
            onRow={(_record, index) => ({
              onClick: () => {
                if (index !== undefined) setCurrentChangeIndex(index);
              },
              style: { cursor: 'pointer' },
            })}
          />
        </Card>
      )}

      {/* 하단 액션 버튼 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Space>
          {onDownloadHwp && (
            <Button
              data-guide="diff-download"
              type="primary"
              icon={<FileWordOutlined />}
              onClick={onDownloadHwp}
            >
              수정본 HWP 다운로드
            </Button>
          )}
        </Space>
      </div>
    </div>
  );
});

export default DiffViewer;
