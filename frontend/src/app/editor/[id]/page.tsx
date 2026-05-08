'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Alert, message, Modal, Tabs } from 'antd';
import { EditOutlined, DiffOutlined, FileExcelOutlined } from '@ant-design/icons';
import DocumentEditor from '@/components/editor/DocumentEditor';
import DiffViewer from '@/components/diff/DiffViewer';
import ExcelUpload from '@/components/upload/ExcelUpload';
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

  const [activeTab, setActiveTab] = useState('edit');
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

  const handleDownloadReport = useCallback(async () => {
    if (!diffData) return;

    const lines: string[] = [];
    lines.push('=== 변경 보고서 ===');
    lines.push(`문서: ${currentDocument?.original_filename ?? ''}`);
    lines.push(`생성일: ${new Date().toLocaleDateString('ko-KR')}`);
    lines.push(`버전: ${diffData.version_number}`);
    lines.push('');
    lines.push('--- 원본 ---');
    lines.push(diffData.original_text);
    lines.push('');
    lines.push('--- 수정본 ---');
    lines.push(modifiedDiffText ?? diffData.modified_text);

    const content = lines.join('\n');
    const defaultName = `변경보고서_${currentDocument?.original_filename ?? 'document'}_v${diffData.version_number}`;

    // File System Access API로 "다른 이름으로 저장" 대화상자 표시
    if ('showSaveFilePicker' in window) {
      try {
        const handle = await (window as unknown as { showSaveFilePicker: (opts: unknown) => Promise<FileSystemFileHandle> }).showSaveFilePicker({
          suggestedName: defaultName,
          types: [
            { description: '텍스트 파일', accept: { 'text/plain': ['.txt'] } },
            { description: 'CSV 파일', accept: { 'text/csv': ['.csv'] } },
            { description: '모든 파일', accept: { 'application/octet-stream': ['.doc', '.hwp'] } },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(content);
        await writable.close();
        message.success('변경 보고서가 저장되었습니다.');
        return;
      } catch (e) {
        // 사용자가 취소한 경우
        if (e instanceof DOMException && e.name === 'AbortError') return;
      }
    }

    // fallback: 브라우저가 showSaveFilePicker를 지원하지 않는 경우
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${defaultName}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('변경 보고서가 다운로드되었습니다.');
  }, [diffData, currentDocument, modifiedDiffText]);

  if (isLoading && !currentDocument) {
    return <LoadingSpinner tip="문서를 불러오는 중..." />;
  }

  // Show error as a banner instead of blocking the entire page.
  // The editor UI will still render below so users can start working.

  const tabItems = [
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
      key: 'excel',
      label: (
        <span>
          <FileExcelOutlined /> 엑셀 일괄 교체
        </span>
      ),
      children: (
        <div style={{ padding: 16 }}>
          <ExcelUpload
            documentId={String(documentId)}
            onUploadComplete={handleExcelUploadComplete}
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
                onRevertAll={handleRevert}
                onSave={handleDiffSave}
                onDownloadReport={handleDownloadReport}
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
