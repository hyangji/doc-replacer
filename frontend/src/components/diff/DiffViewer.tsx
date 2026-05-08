'use client';

import React, { useState, useMemo, useEffect } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { Card, Radio, Button, Space, Typography, Table, Tag, Collapse, Input } from 'antd';
import {
  UpOutlined,
  DownOutlined,
  RollbackOutlined,
  SaveOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;

type ViewMode = 'split' | 'unified';

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
  onSave?: (modifiedText: string) => void;
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
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [currentChangeIndex, setCurrentChangeIndex] = useState(0);

  // Editable modified lines state
  const [modifiedLines, setModifiedLines] = useState<string[]>(
    modifiedContent.split('\n')
  );

  // Reset when modifiedContent prop changes
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

  // Notify parent of modified text changes
  useEffect(() => {
    onModifiedTextChange?.(currentModifiedText);
  }, [currentModifiedText, onModifiedTextChange]);

  // Compute changed lines by comparing original and modified line-by-line
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

  // Revert a single line back to original
  const handleRevertLine = (lineIndex: number) => {
    setModifiedLines((prev) => {
      const next = [...prev];
      next[lineIndex] = originalLines[lineIndex] ?? '';
      return next;
    });
  };

  const changeColumns: ColumnsType<ChangeRecord> = [
    {
      title: '#',
      dataIndex: 'index',
      key: 'index',
      width: 50,
    },
    {
      title: '위치',
      dataIndex: 'line',
      key: 'line',
      width: 80,
      render: (line: number) => `${line}줄`,
    },
    {
      title: '유형',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: ChangeRecord['type']) => (
        <Tag color={changeTypeColorMap[type]}>{type}</Tag>
      ),
    },
    {
      title: '이전 값',
      dataIndex: 'original',
      key: 'original',
      ellipsis: true,
      render: (text: string) => (
        <Text type={text ? undefined : 'secondary'}>{text || '-'}</Text>
      ),
    },
    {
      title: '새 값',
      dataIndex: 'modified',
      key: 'modified',
      ellipsis: true,
      render: (text: string) => (
        <Text type={text ? undefined : 'secondary'}>{text || '-'}</Text>
      ),
    },
    {
      title: '액션',
      key: 'action',
      width: 100,
      render: (_: unknown, record: ChangeRecord) => (
        <Button
          type="link"
          size="small"
          danger
          icon={<RollbackOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            handleRevertLine(record.line - 1);
          }}
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
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Space>
            <Text strong>보기:</Text>
            <Radio.Group
              value={viewMode}
              onChange={(e) => setViewMode(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              <Radio.Button value="split">나란히</Radio.Button>
              <Radio.Button value="unified">통합</Radio.Button>
            </Radio.Group>
          </Space>

          <Space>
            <Button
              size="small"
              icon={<UpOutlined />}
              disabled={changedLines.length === 0}
              onClick={() => navigateChange('prev')}
            >
              이전 변경
            </Button>
            <Button
              size="small"
              icon={<DownOutlined />}
              disabled={changedLines.length === 0}
              onClick={() => navigateChange('next')}
            >
              다음 변경
            </Button>
            {changedLines.length > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {currentChangeIndex + 1}/{changedLines.length}
              </Text>
            )}
          </Space>
        </div>
      </Card>

      {/* Diff 뷰어 */}
      <Card
        size="small"
        styles={{
          body: {
            padding: 0,
            overflow: 'auto',
            /* 텍스트 선택/복사 허용 */
            userSelect: 'text',
            WebkitUserSelect: 'text',
          },
        }}
      >
        <ReactDiffViewer
          oldValue={originalContent}
          newValue={currentModifiedText}
          splitView={viewMode === 'split'}
          leftTitle={originalTitle}
          rightTitle={modifiedTitle}
          compareMethod={DiffMethod.WORDS}
          styles={diffStyles}
          useDarkTheme={false}
        />
      </Card>

      {/* 수정본 직접 편집 */}
      <Collapse
        size="small"
        items={[
          {
            key: 'edit',
            label: '수정본 직접 편집',
            children: (
              <Input.TextArea
                value={currentModifiedText}
                onChange={(e) => {
                  setModifiedLines(e.target.value.split('\n'));
                }}
                autoSize={{ minRows: 10, maxRows: 30 }}
                style={{
                  fontFamily: 'monospace',
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              />
            ),
          },
        ]}
      />

      {/* 변경사항 요약 테이블 */}
      {changedLines.length > 0 && (
        <Card
          size="small"
          title={
            <Title level={5} style={{ margin: 0 }}>
              변경사항 요약 ({changedLines.length}건)
            </Title>
          }
        >
          <Table<ChangeRecord>
            columns={changeColumns}
            dataSource={changedLines}
            pagination={false}
            size="small"
            rowClassName={(_, index) =>
              index === currentChangeIndex ? 'ant-table-row-selected' : ''
            }
            onRow={(_, index) => ({
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
          {changedLines.length > 0 && (
            <Button danger icon={<RollbackOutlined />} onClick={onRevertAll}>
              모두 되돌리기
            </Button>
          )}
          <Button icon={<DownloadOutlined />} onClick={onDownloadReport}>
            변경 보고서 다운로드
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={() => onSave?.(currentModifiedText)}
          >
            저장
          </Button>
        </Space>
      </div>
    </div>
  );
}
