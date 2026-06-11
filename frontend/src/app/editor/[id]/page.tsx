'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Alert, Button, Empty, message, Modal, Space, Spin, Tabs, Tag } from 'antd';
import {
  DiffOutlined,
  TableOutlined,
  FileTextOutlined,
  RollbackOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import DocumentPreview from '@/components/editor/DocumentPreview';
import DiffViewer, { type DiffViewerHandle } from '@/components/diff/DiffViewer';
import ComparisonUpload from '@/components/upload/ComparisonUpload';
import PageHeader from '@/components/common/PageHeader';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useDocumentStore } from '@/lib/stores/documentStore';
import * as api from '@/lib/api';

export default function EditorPage() {
  const params = useParams();
  const router = useRouter();
  const documentId = Number(params.id);

  const {
    currentDocument,
    isLoading,
    error,
    diffData,
    fetchDocument,
    setDiffData,
  } = useDocumentStore();

  const [activeTab, setActiveTab] = useState('preview');
  const [modifiedDiffText, setModifiedDiffText] = useState<string | null>(null);
  // 문서 모드 미저장 손편집 존재 여부(다운로드 전 자동저장 판단용)
  const [docDirty, setDocDirty] = useState(false);
  // 대비표 업로드 패널 초기화용 key(증가시키면 ComparisonUpload가 remount되어 미리보기·구간현황 등 비워짐)
  const [comparisonKey, setComparisonKey] = useState(0);
  const diffViewerRef = useRef<DiffViewerHandle>(null);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    (async () => {
      await fetchDocument(documentId);
      try {
        const diff = await api.getDiff(documentId);
        if (!cancelled) setDiffData(diff);
      } catch {
        // error already shown by interceptor
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, fetchDocument, setDiffData]);

  const handleReset = useCallback(() => {
    Modal.confirm({
      title: '원본으로 초기화',
      content:
        '적용한 대비표와 직접 수정한 내용이 모두 초기화되고 원본 문서로 돌아갑니다. 계속할까요?',
      okText: '초기화',
      cancelText: '취소',
      okButtonProps: { danger: true },
      async onOk() {
        try {
          await api.resetDocument(documentId);
          // 새 버전(원본 내용) 기준으로 비교/문서 갱신
          const diff = await api.getDiff(documentId);
          setDiffData(diff);
          await fetchDocument(documentId);
          // 대비표 탭의 미리보기/구간 처리 현황 등 이전 엑셀 잔여 상태도 함께 비움
          setComparisonKey((k) => k + 1);
          message.success('원본으로 초기화되었습니다.');
        } catch {
          // error already shown by interceptor
        }
      },
    });
  }, [documentId, setDiffData, fetchDocument]);

  const handleExcelUploadComplete = useCallback(() => {
    api.getDiff(documentId)
      .then((diff) => {
        setDiffData(diff);
        setActiveTab('diff');
        // Refresh document to get updated content
        fetchDocument(documentId);
      })
      .catch(() => {
        // error handled by interceptor
      });
  }, [documentId, setDiffData, fetchDocument]);

  // 문서 모드 인라인 편집(save-blocks) 저장 성공 → 새 버전으로 비교/문서 갱신
  const handleDocSaved = useCallback(() => {
    api.getDiff(documentId)
      .then((diff) => {
        setDiffData(diff);
        fetchDocument(documentId);
      })
      .catch(() => {
        // error handled by interceptor
      });
  }, [documentId, setDiffData, fetchDocument]);

  const handleDownloadHwp = useCallback(async () => {
    if (!diffData) return;

    const diffDirty =
      modifiedDiffText != null &&
      modifiedDiffText !== diffData.modified_text;

    try {
      // 문서 모드 미저장 손편집(셀 단위 save-blocks)이 있으면 먼저 자동저장
      const docHasDirty =
        docDirty || (diffViewerRef.current?.hasDocDirty() ?? false);
      if (docHasDirty && diffViewerRef.current) {
        message.loading({ content: '문서 편집 저장 중...', key: 'download-hwp' });
        const saved = await diffViewerRef.current.saveDocBlocks();
        if (saved) {
          await fetchDocument(documentId);
        }
      }

      // 미저장 Diff(텍스트) 편집이 있으면 다운로드 전에 자동저장 후 새로고침
      if (diffDirty) {
        message.loading({ content: '변경사항 저장 중...', key: 'download-hwp' });
        await api.saveDocument(documentId, modifiedDiffText as string);
        await fetchDocument(documentId);
      }

      message.loading({ content: '수정본 다운로드 중...', key: 'download-hwp' });
      const { blob, filename } = await api.downloadDocument(documentId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      message.success({ content: '수정본 HWP 다운로드가 시작됩니다.', key: 'download-hwp' });
    } catch {
      // 에러 메시지는 인터셉터에서 표시됨 (저장 실패 시 다운로드 중단)
      message.destroy('download-hwp');
    }
  }, [
    documentId,
    diffData,
    modifiedDiffText,
    docDirty,
    fetchDocument,
  ]);

  // 상태 배지: diffData 기준으로 원본/적용됨 판정 + 변경 라인 수 계산
  const isApplied =
    diffData != null && diffData.original_text !== diffData.modified_text;
  const changedLineCount = (() => {
    if (!isApplied || !diffData) return 0;
    const origLines = diffData.original_text.split('\n');
    const modLines = diffData.modified_text.split('\n');
    const maxLen = Math.max(origLines.length, modLines.length);
    let count = 0;
    for (let i = 0; i < maxLen; i++) {
      if ((origLines[i] ?? '') !== (modLines[i] ?? '')) count += 1;
    }
    return count;
  })();
  const statusBadge = diffData ? (
    isApplied ? (
      <Tag color="processing">
        대비표 적용됨{changedLineCount > 0 ? ` (${changedLineCount}건)` : ''}
      </Tag>
    ) : (
      <Tag>원본</Tag>
    )
  ) : null;

  // 상태 배지 + '원본으로 초기화' + '새 문서 열기'(다른 원본 HWP 업로드/선택 진입점)
  const headerActions = (
    <Space size={8} align="center">
      {statusBadge}
      <Button
        size="small"
        danger
        icon={<RollbackOutlined />}
        disabled={!isApplied}
        onClick={handleReset}
      >
        원본으로 초기화
      </Button>
      <Button
        size="small"
        icon={<FolderOpenOutlined />}
        onClick={() => router.push('/documents')}
      >
        새 문서 열기
      </Button>
    </Space>
  );

  if (isLoading && !currentDocument) {
    return <LoadingSpinner tip="문서를 불러오는 중..." />;
  }

  // Show error as a banner instead of blocking the entire page.
  // The editor UI will still render below so users can start working.

  const tabItems = [
    {
      key: 'preview',
      label: (
        <span>
          <FileTextOutlined /> 미리보기
        </span>
      ),
      children: (
        <DocumentPreview
          key={currentDocument?.updated_at ?? documentId}
          documentId={documentId}
        />
      ),
    },
    {
      key: 'comparison',
      label: (
        <span>
          <TableOutlined /> 대비표 일괄 수정
        </span>
      ),
      children: (
        <div style={{ padding: 16 }}>
          <ComparisonUpload
            key={comparisonKey}
            documentId={String(documentId)}
            onApplyComplete={handleExcelUploadComplete}
            hasExistingWork={
              diffData != null &&
              diffData.original_text !== diffData.modified_text
            }
          />
        </div>
      ),
    },
    {
      key: 'diff',
      label: (
        <span>
          <DiffOutlined /> Diff 비교
        </span>
      ),
      children:
        diffData == null ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <Spin tip="비교 데이터를 불러오는 중..." />
          </div>
        ) : !isApplied ? (
          <div style={{ padding: 48 }}>
            <Empty
              description={
                <span>
                  아직 대비표가 적용되지 않았습니다.
                  <br />
                  먼저 &lsquo;대비표 일괄 수정&rsquo; 탭에서 엑셀 파일을 업로드하세요.
                </span>
              }
            >
              <Button
                type="primary"
                icon={<TableOutlined />}
                onClick={() => setActiveTab('comparison')}
              >
                대비표 일괄 수정으로 이동
              </Button>
            </Empty>
          </div>
        ) : (
          <DiffViewer
            ref={diffViewerRef}
            originalContent={diffData.original_text}
            modifiedContent={diffData.modified_text}
            originalTitle="원본 문서"
            modifiedTitle="수정된 문서"
            documentId={documentId}
            modifiedVersion={diffData.version_number}
            onDownloadHwp={handleDownloadHwp}
            onModifiedTextChange={setModifiedDiffText}
            onDocSaved={handleDocSaved}
            onDocDirtyChange={setDocDirty}
          />
        ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title={currentDocument?.original_filename ?? '문서 편집기'}
        breadcrumb={[
          { title: '문서 작업', href: '/documents' },
          { title: currentDocument?.original_filename ?? '문서 편집기' },
        ]}
        actions={headerActions}
      />

      {error && !currentDocument && (
        <Alert
          message="문서 로드 실패"
          description={error}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        style={{ flex: 1 }}
      />
    </div>
  );
}
