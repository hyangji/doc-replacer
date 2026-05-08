'use client';

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { Card, Radio, Button, Space, Typography, Table, Tag, Input } from 'antd';
import {
  UpOutlined,
  DownOutlined,
  RollbackOutlined,
  SaveOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;
const { TextArea } = Input;

type ViewMode = 'compare' | 'edit';

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
  onRevertAll?: () => void;
  onSave?: (modifiedText?: string) => void;
  onDownloadReport?: () => void;
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

export default function DiffViewer({
  originalContent,
  modifiedContent,
  originalTitle = '원본 문서',
  modifiedTitle = '수정된 문서',
  onRevertAll,
  onSave,
  onDownloadReport,
  onModifiedTextChange,
}: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('compare');
  const [currentChangeIndex, setCurrentChangeIndex] = useState(0);
  const originalRef = useRef<HTMLDivElement>(null);
  const modifiedRef = useRef<HTMLTextAreaElement>(null);

  const [modifiedLines, setModifiedLines] = useState<string[]>(
    modifiedContent.split('\n')
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

  // 변경된 줄 인덱스 Set (하이라이트용)
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

  const changedLines = useMemo(() => {
    const changes: ChangeRecord[] = [];
    const maxLen = Math.max(originalLines.length, modifiedLines.length);
    for (let i = 0; i < maxLen; i++) {
      const orig = originalLines[i] ?? '';
      const mod = modifiedLines[i] ?? '';
      if (orig !== mod) {
        let type: ChangeRecord['type'] = '수정';
        if (i >= originalLines.length) type = '추가';
        else if (i >= modifiedLines.length) type = '삭제';
        changes.push({
          key: String(i),
          index: changes.length + 1,
          line: i + 1,
          type,
          original: orig,
          modified: mod,
        });
      }
    }
    return changes;
  }, [originalLines, modifiedLines]);

  const navigateChange = (direction: 'prev' | 'next') => {
    if (changedLines.length === 0) return;
    if (direction === 'next') {
      setCurrentChangeIndex((prev) => (prev + 1) % changedLines.length);
    } else {
      setCurrentChangeIndex((prev) => (prev - 1 + changedLines.length) % changedLines.length);
    }
  };

  const handleRevertLine = (lineIndex: number) => {
    setModifiedLines((prev) => {
      const next = [...prev];
      next[lineIndex] = originalLines[lineIndex] ?? '';
      return next;
    });
  };

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
      title: '', key: 'action', width: 80,
      render: (_: unknown, record: ChangeRecord) => (
        <Button
          type="link"
          size="small"
          danger
          icon={<RollbackOutlined />}
          onClick={(e) => { e.stopPropagation(); handleRevertLine(record.line - 1); }}
        >
          되돌리기
        </Button>
      ),
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
                    {line || '\u00A0'}
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
              {modifiedTitle} (편집 가능)
            </div>
            <TextArea
              ref={modifiedRef as unknown as React.Ref<HTMLTextAreaElement>}
              value={currentModifiedText}
              onChange={(e) => setModifiedLines(e.target.value.split('\n'))}
              onScroll={handleModifiedScroll}
              style={{
                flex: 1,
                resize: 'none',
                fontFamily: 'monospace',
                fontSize: 13,
                lineHeight: '24px',
                padding: '0 8px',
                borderRadius: 0,
                border: '1px solid #91caff',
                borderTop: 0,
              }}
            />
          </div>
        </div>
      )}

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
            rowClassName={(_, index) => index === currentChangeIndex ? 'ant-table-row-selected' : ''}
            onRow={(_, index) => ({
              onClick: () => { if (index !== undefined) setCurrentChangeIndex(index); },
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
          <Button icon={<DownloadOutlined />} onClick={onDownloadReport}>변경 보고서 다운로드</Button>
          <Button type="primary" icon={<SaveOutlined />} onClick={() => onSave?.(currentModifiedText)}>저장</Button>
        </Space>
      </div>
    </div>
  );
}
