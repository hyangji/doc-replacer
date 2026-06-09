'use client';

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { diffWords } from 'diff';
import { Card, Radio, Button, Space, Typography, Table, Tag, Spin } from 'antd';
import {
  UpOutlined,
  DownOutlined,
  RollbackOutlined,
  SaveOutlined,
  FileWordOutlined,
  EditOutlined,
  EyeOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getDocumentHtml, getDocumentCompareHtml } from '@/lib/api';

const { Title, Text } = Typography;

type ViewMode = 'compare' | 'edit' | 'document';

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
  onRevertAll?: () => void;
  onSave?: (modifiedText?: string) => void;
  onDownloadHwp?: () => void;
  onModifiedTextChange?: (text: string) => void;
}

const changeTypeColorMap: Record<ChangeRecord['type'], string> = {
  수정: 'orange',
  삭제: 'red',
  추가: 'green',
};

const diffStyles = {
  variables: {
    light: {
      diffViewerBackground: '#FFFFFF',
      addedBackground: '#E6FFE6',
      addedColor: '#237804',
      removedBackground: '#FFE6E6',
      removedColor: '#CF1322',
      wordAddedBackground: '#B7EB8F',
      wordRemovedBackground: '#FFA39E',
      addedGutterBackground: '#D9F7D9',
      removedGutterBackground: '#F7D9D9',
      gutterBackground: '#F7F7F7',
      gutterBackgroundDark: '#F0F0F0',
      codeFoldBackground: '#F5F5F5',
      codeFoldGutterBackground: '#EBEBEB',
    },
  },
};

// 한 줄을 토큰(단어) 단위로 비교해, side에 해당하는 세그먼트만 강조한 span 배열 반환.
// side === 'old': 원본 줄에서 삭제/변경된 토큰을 빨강+취소선으로 강조.
// side === 'new': 수정본 줄에서 추가/변경된 토큰을 초록+굵게 강조.
function renderInlineDiff(
  original: string,
  modified: string,
  side: 'old' | 'new'
): React.ReactNode[] {
  const segments = diffWords(original, modified);
  const nodes: React.ReactNode[] = [];

  segments.forEach((seg, idx) => {
    if (side === 'old') {
      // 원본 쪽: 공통 토큰 + 삭제된 토큰만 렌더 (추가된 토큰은 원본에 없음)
      if (seg.added) return;
      if (seg.removed) {
        nodes.push(
          <span
            key={idx}
            style={{
              background: '#ffd6d6',
              color: '#cf1322',
              textDecoration: 'line-through',
            }}
          >
            {seg.value}
          </span>
        );
      } else {
        nodes.push(<span key={idx}>{seg.value}</span>);
      }
    } else {
      // 수정본 쪽: 공통 토큰 + 추가된 토큰만 렌더 (삭제된 토큰은 수정본에 없음)
      if (seg.removed) return;
      if (seg.added) {
        nodes.push(
          <span
            key={idx}
            style={{
              background: '#b7eb8f',
              color: '#135200',
              fontWeight: 700,
            }}
          >
            {seg.value}
          </span>
        );
      } else {
        nodes.push(<span key={idx}>{seg.value}</span>);
      }
    }
  });

  return nodes;
}

export default function DiffViewer({
  originalContent,
  modifiedContent,
  originalTitle = '원본 문서',
  modifiedTitle = '수정된 문서',
  documentId,
  originalVersion = 1,
  modifiedVersion,
  onRevertAll,
  onSave,
  onDownloadHwp,
  onModifiedTextChange,
}: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('compare');
  const [currentChangeIndex, setCurrentChangeIndex] = useState(0);
  const originalRef = useRef<HTMLDivElement>(null);
  const modifiedRef = useRef<HTMLTextAreaElement>(null);

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

  // 변경된 줄 인덱스 Set (현재 상태 기준 하이라이트용)
  const changedLineIndices = useMemo(() => {
    const set = new Set<number>();
    const maxLen = Math.max(originalLines.length, modifiedLines.length);
    for (let i = 0; i < maxLen; i++) {
      if ((originalLines[i] ?? '') !== (modifiedLines[i] ?? '')) {
        set.add(i);
      }
    }
    return set;
  }, [originalLines, modifiedLines]);

  // 원래 수정본에서 변경되었던 줄 인덱스 Set (되돌리기 버튼 표시용 - 원본 vs 최초 수정본)
  const originallyChangedIndices = useMemo(() => {
    const set = new Set<number>();
    const maxLen = Math.max(originalLines.length, originalModifiedLines.length);
    for (let i = 0; i < maxLen; i++) {
      if ((originalLines[i] ?? '') !== (originalModifiedLines[i] ?? '')) {
        set.add(i);
      }
    }
    return set;
  }, [originalLines, originalModifiedLines]);

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

  const navigateChange = (direction: 'prev' | 'next') => {
    if (changedLines.length === 0) return;
    let newIndex: number;
    if (direction === 'next') {
      newIndex = (currentChangeIndex + 1) % changedLines.length;
    } else {
      newIndex = (currentChangeIndex - 1 + changedLines.length) % changedLines.length;
    }
    setCurrentChangeIndex(newIndex);
    scrollToLine(changedLines[newIndex].line);
  };

  const handleRevertLine = (lineIndex: number) => {
    setModifiedLines((prev) => {
      const next = [...prev];
      next[lineIndex] = originalLines[lineIndex] ?? '';
      return next;
    });
  };

  // 수정본으로 되돌리기
  const handleRestoreLine = (lineIndex: number) => {
    setModifiedLines((prev) => {
      const next = [...prev];
      next[lineIndex] = originalModifiedLines[lineIndex] ?? '';
      return next;
    });
  };

  // 해당 줄이 원본으로 되돌려진 상태인지 확인
  const isRevertedToOriginal = useCallback((lineIndex: number) => {
    const orig = originalLines[lineIndex] ?? '';
    const origMod = originalModifiedLines[lineIndex] ?? '';
    const current = modifiedLines[lineIndex] ?? '';
    // 원래 수정본과 원본이 다르고, 현재 원본과 같으면 되돌려진 상태
    return orig !== origMod && current === orig;
  }, [originalLines, originalModifiedLines, modifiedLines]);

  // diff viewer 컨테이너 ref (스크롤용)
  const diffContainerRef = useRef<HTMLDivElement>(null);

  // 변경사항 테이블 row 클릭 시 해당 위치로 스크롤
  const scrollToLine = useCallback((lineNumber: number) => {
    const lineIndex = lineNumber - 1;
    const LINE_HEIGHT = 24;

    if (viewMode === 'edit') {
      // 편집 모드: 양쪽 패널 스크롤
      const scrollTop = lineIndex * LINE_HEIGHT - 100;
      if (originalRef.current) {
        originalRef.current.scrollTop = Math.max(0, scrollTop);
      }
      if (modifiedRef.current) {
        (modifiedRef.current as unknown as HTMLDivElement).scrollTop = Math.max(0, scrollTop);
      }
    } else {
      // 비교 모드: diff viewer 내에서 해당 줄로 스크롤
      if (diffContainerRef.current) {
        const rows = diffContainerRef.current.querySelectorAll('tr');
        for (const row of rows) {
          const lineNumCell = row.querySelector('td:first-child pre');
          if (lineNumCell && lineNumCell.textContent?.trim() === String(lineNumber)) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // 하이라이트 효과
            row.style.transition = 'background 0.3s';
            row.style.background = '#fff7e6';
            setTimeout(() => { row.style.background = ''; }, 1500);
            break;
          }
        }
      }
    }
  }, [viewMode]);

  // 편집 모드에서 스크롤 동기화
  const handleOriginalScroll = useCallback(() => {
    if (originalRef.current && modifiedRef.current) {
      modifiedRef.current.scrollTop = originalRef.current.scrollTop;
    }
  }, []);

  const handleModifiedScroll = useCallback(() => {
    if (originalRef.current && modifiedRef.current) {
      originalRef.current.scrollTop = modifiedRef.current.scrollTop;
    }
  }, []);

  // --- 문서 모드: 좌/우 HTML 패널 스크롤 동기화 ---
  const docOriginalRef = useRef<HTMLDivElement>(null);
  const docModifiedRef = useRef<HTMLDivElement>(null);
  // 프로그래밍적 스크롤 중 상대 onScroll을 무시해 무한 루프(떨림) 방지
  const isSyncingDocScrollRef = useRef(false);

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

  // --- 문서 모드: 표 보존 HTML 렌더 ---
  const [originalHtml, setOriginalHtml] = useState<string | null>(null);
  const [modifiedHtml, setModifiedHtml] = useState<string | null>(null);
  const [htmlLoading, setHtmlLoading] = useState(false);
  const [htmlError, setHtmlError] = useState<string | null>(null);
  // 같은 요청 재호출 방지용 캐시
  //  - 단일 버전 렌더: key = `v${version}`, value = html
  //  - 비교(하이라이트) 렌더: key = `cmp${base}|${target}`, value = {original_html, modified_html}
  const htmlCacheRef = useRef<Map<string, string>>(new Map());
  const compareCacheRef = useRef<
    Map<string, { original_html: string; modified_html: string }>
  >(new Map());

  useEffect(() => {
    if (viewMode !== 'document' || documentId == null) return;

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
      const key = `cmp${base}|${target}`;
      const cached = compareCacheRef.current.get(key);
      if (cached != null) return cached;
      const result = await getDocumentCompareHtml(documentId, base, target);
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
  }, [viewMode, documentId, originalVersion, modifiedVersion]);

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
    {
      title: '', key: 'action', width: 140,
      render: (_: unknown, record: ChangeRecord) => {
        const reverted = isRevertedToOriginal(record.line - 1);
        return reverted ? (
          <Button
            type="link"
            size="small"
            style={{ color: '#1677ff' }}
            icon={<RollbackOutlined />}
            onClick={(e) => { e.stopPropagation(); handleRestoreLine(record.line - 1); }}
          >
            수정본으로
          </Button>
        ) : (
          <Button
            type="link"
            size="small"
            danger
            icon={<RollbackOutlined />}
            onClick={(e) => { e.stopPropagation(); handleRevertLine(record.line - 1); }}
          >
            원본으로
          </Button>
        );
      },
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 툴바 */}
      <Card size="small">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Text strong>모드:</Text>
            <Radio.Group
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              <Radio.Button value="compare"><EyeOutlined /> 비교</Radio.Button>
              <Radio.Button value="edit"><EditOutlined /> 편집</Radio.Button>
              {documentId != null && (
                <Radio.Button value="document"><FileTextOutlined /> 문서</Radio.Button>
              )}
            </Radio.Group>
          </Space>

          <Space>
            <Button size="small" icon={<UpOutlined />} disabled={changedLines.length === 0} onClick={() => navigateChange('prev')}>이전</Button>
            <Button size="small" icon={<DownOutlined />} disabled={changedLines.length === 0} onClick={() => navigateChange('next')}>다음</Button>
            {changedLines.length > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>{currentChangeIndex + 1}/{changedLines.length}</Text>
            )}
          </Space>
        </div>
      </Card>

      {/* 비교 모드: react-diff-viewer */}
      {viewMode === 'compare' && (
        <Card
          ref={diffContainerRef}
          size="small"
          styles={{ body: { padding: 0, overflow: 'auto', userSelect: 'text', WebkitUserSelect: 'text' } }}
        >
          <ReactDiffViewer
            oldValue={originalContent}
            newValue={currentModifiedText}
            splitView
            leftTitle={originalTitle}
            rightTitle={modifiedTitle}
            compareMethod={DiffMethod.WORDS}
            styles={diffStyles}
            useDarkTheme={false}
          />
        </Card>
      )}

      {/* 편집 모드: 원본(읽기 전용) | 수정본(편집 가능) */}
      {viewMode === 'edit' && (
        <div style={{ display: 'flex', gap: 2, height: 'calc(100vh - 360px)', minHeight: 400 }}>
          {/* 좌측: 원본 (읽기 전용) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{
              padding: '8px 12px',
              background: '#f5f5f5',
              borderBottom: '1px solid #d9d9d9',
              fontWeight: 600,
              fontSize: 13,
            }}>
              {originalTitle} (읽기 전용)
            </div>
            <div
              ref={originalRef}
              onScroll={handleOriginalScroll}
              style={{
                flex: 1,
                overflow: 'auto',
                border: '1px solid #d9d9d9',
                borderTop: 0,
                background: '#fafafa',
              }}
            >
              {originalLines.map((line, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    minHeight: 24,
                    lineHeight: '24px',
                    background: changedLineIndices.has(i) ? '#FFE6E6' : 'transparent',
                    borderLeft: changedLineIndices.has(i) ? '3px solid #ff4d4f' : '3px solid transparent',
                  }}
                >
                  <span style={{
                    width: 45,
                    minWidth: 45,
                    textAlign: 'right',
                    padding: '0 8px 0 4px',
                    color: '#999',
                    fontSize: 12,
                    background: '#f0f0f0',
                    userSelect: 'none',
                  }}>
                    {i + 1}
                  </span>
                  <span style={{
                    flex: 1,
                    padding: '0 8px',
                    fontFamily: 'monospace',
                    fontSize: 13,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    userSelect: 'text',
                  }}>
                    {changedLineIndices.has(i)
                      ? renderInlineDiff(line, modifiedLines[i] ?? '', 'old')
                      : (line || '\u00A0')}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* 우측: 수정본 (편집 가능) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{
              padding: '8px 12px',
              background: '#e6f4ff',
              borderBottom: '1px solid #91caff',
              fontWeight: 600,
              fontSize: 13,
              color: '#1677ff',
            }}>
              {modifiedTitle} (편집 가능 - 클릭하여 수정)
            </div>
            <div
              ref={modifiedRef as unknown as React.RefObject<HTMLDivElement>}
              onScroll={handleModifiedScroll}
              style={{
                flex: 1,
                overflow: 'auto',
                border: '1px solid #91caff',
                borderTop: 0,
                background: '#fff',
              }}
            >
              {modifiedLines.map((line, i) => {
                const isChanged = changedLineIndices.has(i);
                const isReverted = !isChanged && originallyChangedIndices.has(i) && isRevertedToOriginal(i);
                return (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    minHeight: 24,
                    lineHeight: '24px',
                    background: isChanged ? '#E6FFE6' : isReverted ? '#e6f4ff' : 'transparent',
                    borderLeft: isChanged ? '3px solid #52c41a' : isReverted ? '3px solid #1677ff' : '3px solid transparent',
                  }}
                >
                  <span style={{
                    width: 45,
                    minWidth: 45,
                    textAlign: 'right',
                    padding: '0 8px 0 4px',
                    color: '#999',
                    fontSize: 12,
                    background: '#f0f0f0',
                    userSelect: 'none',
                  }}>
                    {i + 1}
                  </span>
                  <span
                    contentEditable
                    suppressContentEditableWarning
                    onBlur={(e) => {
                      const newText = e.currentTarget.textContent ?? '';
                      if (newText !== modifiedLines[i]) {
                        setModifiedLines(prev => {
                          const next = [...prev];
                          next[i] = newText;
                          return next;
                        });
                      }
                    }}
                    style={{
                      flex: 1,
                      padding: '0 8px',
                      fontFamily: 'monospace',
                      fontSize: 13,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      outline: 'none',
                      cursor: 'text',
                    }}
                  >
                    {isChanged
                      ? renderInlineDiff(originalLines[i] ?? '', line, 'new')
                      : (line || '\u00A0')}
                  </span>
                  {/* 현재 수정된 줄: 원본으로 되돌리기 */}
                  {changedLineIndices.has(i) && originallyChangedIndices.has(i) && (
                    <span
                      style={{ padding: '0 4px', cursor: 'pointer', color: '#ff4d4f', userSelect: 'none' }}
                      title="원본으로 되돌리기"
                      onClick={() => handleRevertLine(i)}
                    >
                      <RollbackOutlined />
                    </span>
                  )}
                  {/* 원본으로 되돌려진 줄: 수정본으로 되돌리기 */}
                  {!changedLineIndices.has(i) && originallyChangedIndices.has(i) && isRevertedToOriginal(i) && (
                    <span
                      style={{ padding: '0 4px', cursor: 'pointer', color: '#1677ff', userSelect: 'none' }}
                      title="수정본으로 되돌리기"
                      onClick={() => handleRestoreLine(i)}
                    >
                      <RollbackOutlined />
                    </span>
                  )}
                </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 문서 모드: 표 보존 HTML 좌우 렌더 */}
      {viewMode === 'document' && (
        <>
          {htmlLoading && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
              <Spin tip="문서를 불러오는 중..." />
            </div>
          )}
          {!htmlLoading && htmlError && (
            <Card size="small">
              <Text type="danger">{htmlError}</Text>
            </Card>
          )}
          {!htmlLoading && !htmlError && (
            <div style={{ display: 'flex', gap: 2, height: 'calc(100vh - 360px)', minHeight: 400 }}>
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

              {/* 우측: 수정본 HTML */}
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{
                  padding: '8px 12px',
                  background: '#e6f4ff',
                  borderBottom: '1px solid #91caff',
                  fontWeight: 600,
                  fontSize: 13,
                  color: '#1677ff',
                }}>
                  {modifiedTitle}
                </div>
                <div
                  ref={docModifiedRef}
                  onScroll={() => syncDocScroll('modified')}
                  className="doc-html-render doc-modified"
                  style={{
                    flex: 1,
                    overflow: 'auto',
                    border: '1px solid #91caff',
                    borderTop: 0,
                    background: '#fff',
                    padding: 12,
                    fontSize: 13,
                  }}
                  dangerouslySetInnerHTML={{ __html: modifiedHtml ?? '' }}
                />
              </div>
            </div>
          )}
        </>
      )}

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
            .doc-modified .hwp-changed {
              background: #b7eb8f;
              color: #135200;
              font-weight: 700;
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
            onRow={(record, index) => ({
              onClick: () => {
                if (index !== undefined) setCurrentChangeIndex(index);
                scrollToLine(record.line);
              },
              style: { cursor: 'pointer' },
            })}
          />
        </Card>
      )}

      {/* 하단 액션 버튼 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Space>
          {changedLines.length > 0 && (
            <Button danger icon={<RollbackOutlined />} onClick={onRevertAll}>모두 되돌리기</Button>
          )}
          {onDownloadHwp && (
            <Button icon={<FileWordOutlined />} onClick={onDownloadHwp}>수정본 HWP 다운로드</Button>
          )}
          <Button type="primary" icon={<SaveOutlined />} onClick={() => onSave?.(currentModifiedText)}>저장</Button>
        </Space>
      </div>
    </div>
  );
}
