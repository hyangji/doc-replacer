'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Alert, message, Modal, Tabs } from 'antd';
import { EditOutlined, DiffOutlined, TableOutlined, FileTextOutlined } from '@ant-design/icons';
import DocumentEditor from '@/components/editor/DocumentEditor';
import DocumentPreview from '@/components/editor/DocumentPreview';
import DiffViewer from '@/components/diff/DiffViewer';
import ComparisonUpload from '@/components/upload/ComparisonUpload';
import PageHeader from '@/components/common/PageHeader';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useDocumentStore } from '@/lib/stores/documentStore';
import * as api from '@/lib/api';

export default function EditorPage() {
  const params = useParams();
  const documentId = Number(params.id);

  const {
    currentDocument,
    isLoading,
    error,
    diffData,
    fetchDocument,
    saveDocument,
    revertDocument,
    setDiffData,
  } = useDocumentStore();

  const [activeTab, setActiveTab] = useState('preview');
  const [editorContent, setEditorContent] = useState('');
  const [modifiedDiffText, setModifiedDiffText] = useState<string | null>(null);

  useEffect(() => {
    if (documentId) {
      fetchDocument(documentId);
    }
  }, [documentId, fetchDocument]);

  // Sync editor content when document loads
  useEffect(() => {
    if (currentDocument?.content_text != null) {
      setEditorContent(currentDocument.content_text);
    }
  }, [currentDocument?.content_text]);

  const handleSave = useCallback(
    async (content: string) => {
      try {
        await saveDocument(documentId, content);
        message.success('저장되었습니다.');
      } catch {
        // error already shown by interceptor
      }
    },
    [documentId, saveDocument],
  );

  const handleRevert = useCallback(() => {
    if (!currentDocument || currentDocument.versions.length === 0) {
      message.warning('되돌릴 버전이 없습니다.');
      return;
    }
    const latestVersion = currentDocument.versions[0];
    Modal.confirm({
      title: '문서 되돌리기',
      content: `버전 ${latestVersion.version_number}(으)로 되돌리시겠습니까?`,
      okText: '되돌리기',
      cancelText: '취소',
      async onOk() {
        try {
          await revertDocument(documentId, latestVersion.version_number);
          message.success('문서가 되돌려졌습니다.');
        } catch {
          // error already shown by interceptor
        }
      },
    });
  }, [documentId, currentDocument, revertDocument]);

  const handleConvert = useCallback(
    async (format: 'docx' | 'pdf') => {
      try {
        message.loading({ content: '변환 중...', key: 'convert' });
        const blob = await api.convertDocument(documentId, format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${currentDocument?.original_filename ?? 'document'}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
        message.success({ content: '변환 완료. 다운로드가 시작됩니다.', key: 'convert' });
      } catch {
        message.error({ content: '변환에 실패했습니다.', key: 'convert' });
      }
    },
    [documentId, currentDocument],
  );

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

  const handleDiffSave = useCallback(async (textFromDiff?: string) => {
    if (!diffData) {
      message.warning('비교할 데이터가 없습니다.');
      return;
    }
    try {
      const textToSave = textFromDiff || modifiedDiffText || diffData.modified_text;
      await api.saveDocument(documentId, textToSave);
      message.success('저장되었습니다.');
      await fetchDocument(documentId);
    } catch {
      message.error('저장에 실패했습니다.');
    }
  }, [documentId, diffData, modifiedDiffText, fetchDocument]);

  const handleDownloadHwp = useCallback(async () => {
    if (!diffData) return;

    // 미저장 편집 자동저장 판정
    const editorDirty = editorContent !== (currentDocument?.content_text ?? '');
    const diffDirty =
      modifiedDiffText != null &&
      diffData != null &&
      modifiedDiffText !== diffData.modified_text;

    // 두 곳에서 모두 수정 → 충돌 위험. 데이터 손실 방지 위해 중단.
    if (editorDirty && diffDirty) {
      message.warning(
        '편집 탭과 Diff에서 모두 수정했습니다. 먼저 저장(또는 한쪽 정리) 후 다운로드해 주세요.',
      );
      return;
    }

    try {
      // 미저장 편집이 있으면 다운로드 전에 자동저장 후 새로고침
      if (editorDirty || diffDirty) {
        message.loading({ content: '변경사항 저장 중...', key: 'download-hwp' });
        if (editorDirty) {
          await saveDocument(documentId, editorContent);
        } else {
          await api.saveDocument(documentId, modifiedDiffText as string);
        }
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
    editorContent,
    currentDocument?.content_text,
    modifiedDiffText,
    saveDocument,
    fetchDocument,
  ]);

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
      key: 'edit',
      label: (
        <span>
          <EditOutlined /> 편집
        </span>
      ),
      children: (
        <div style={{ height: 'calc(100vh - 220px)' }}>
          <DocumentEditor
            content={editorContent}
            onChange={setEditorContent}
            onSave={handleSave}
            documentId={String(documentId)}
          />
        </div>
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
            documentId={String(documentId)}
            onApplyComplete={handleExcelUploadComplete}
          />
        </div>
      ),
    },
    ...(diffData
      ? [
          {
            key: 'diff',
            label: (
              <span>
                <DiffOutlined /> Diff 비교
              </span>
            ),
            children: (
              <DiffViewer
                originalContent={diffData.original_text}
                modifiedContent={diffData.modified_text}
                originalTitle="원본 문서"
                modifiedTitle="수정된 문서"
                documentId={documentId}
                modifiedVersion={diffData.version_number}
                onRevertAll={handleRevert}
                onSave={handleDiffSave}
                onDownloadHwp={handleDownloadHwp}
                onModifiedTextChange={setModifiedDiffText}
              />
            ),
          },
        ]
      : []),
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title={currentDocument?.original_filename ?? '문서 편집기'}
        breadcrumb={[
          { title: '홈', href: '/' },
          { title: currentDocument?.original_filename ?? '문서 편집기' },
        ]}
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
