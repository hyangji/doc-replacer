'use client';

import React, { useEffect, useState } from 'react';
import { Alert } from 'antd';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { getDocumentHtml } from '@/lib/api';

interface DocumentPreviewProps {
  documentId: number;
  version?: number;
}

export default function DocumentPreview({ documentId, version }: DocumentPreviewProps) {
  const [html, setHtml] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setHasError(false);

    getDocumentHtml(documentId, version)
      .then((result) => {
        if (cancelled) return;
        setHtml(result ?? '');
      })
      .catch(() => {
        if (cancelled) return;
        setHasError(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [documentId, version]);

  if (loading) {
    return <LoadingSpinner tip="문서를 불러오는 중..." />;
  }

  const isEmpty = !html || html.trim().length === 0;

  return (
    <div style={{ height: 'calc(100vh - 220px)', display: 'flex', flexDirection: 'column' }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="현재 최신 상태의 문서입니다 (원본 아님)"
        description="대비표 적용·편집한 내용이 모두 반영된 모습입니다. 원본과 무엇이 바뀌었는지 비교하려면 'Diff 비교' 탭을, 원본으로 되돌리려면 상단 '원본으로 초기화'를 이용하세요."
      />

      {(hasError || isEmpty) && (
        <Alert
          message="표 서식을 불러오지 못했습니다. 편집 탭에서 텍스트로 확인하세요."
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      {!hasError && !isEmpty && (
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            background: '#f0f2f5',
            padding: 24,
          }}
        >
          <div
            className="doc-preview-render"
            style={{
              maxWidth: 900,
              margin: '0 auto',
              background: '#fff',
              padding: '40px 48px',
              borderRadius: 4,
              boxShadow: '0 1px 4px rgba(0, 0, 0, 0.12)',
            }}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </div>
      )}

      <style
        dangerouslySetInnerHTML={{
          __html: `
            .doc-preview-render {
              font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                'Malgun Gothic', sans-serif;
              font-size: 14px;
              line-height: 1.7;
              color: #1f1f1f;
              word-break: break-word;
            }
            .doc-preview-render p {
              margin: 0 0 8px;
            }
            .doc-preview-render table {
              border-collapse: collapse;
              width: 100%;
              max-width: 100%;
              margin: 12px auto;
            }
            .doc-preview-render table,
            .doc-preview-render td,
            .doc-preview-render th {
              border: 1px solid #bfbfbf;
            }
            .doc-preview-render td,
            .doc-preview-render th {
              padding: 6px 10px;
              font-size: 13px;
              vertical-align: top;
            }
            .doc-preview-render th,
            .doc-preview-render thead td,
            .doc-preview-render tr:first-child td {
              background: #fafafa;
              font-weight: 600;
              text-align: center;
            }
          `,
        }}
      />
    </div>
  );
}
