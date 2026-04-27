'use client';

import React, { useEffect, useCallback } from 'react';
import { Typography, Table, Card, Space, Button, Tag, message, Modal } from 'antd';
import {
  FileTextOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRouter } from 'next/navigation';
import { useDocumentStore } from '@/lib/stores/documentStore';
import { uploadDocument } from '@/lib/api';
import type { DocumentListItem } from '@/types/document';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import FileUpload from '@/components/upload/FileUpload';
import PageHeader from '@/components/common/PageHeader';
import type { UploadFile } from 'antd';

const { Title } = Typography;

const fileTypeColorMap: Record<string, string> = {
  hwp: 'blue',
  hwpx: 'geekblue',
  xlsx: 'green',
  xls: 'green',
  docx: 'purple',
  doc: 'purple',
};

export default function DocumentsPage() {
  const router = useRouter();
  const { documents, isLoading, error, fetchDocuments, deleteDocument: deleteDoc } = useDocumentStore();

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUploadComplete = useCallback(
    (file: UploadFile) => {
      const response = file.response as { id?: number } | undefined;
      if (response?.id) {
        message.success(`${file.name} 업로드 완료`);
        router.push(`/editor/${response.id}`);
      } else {
        fetchDocuments();
      }
    },
    [router, fetchDocuments],
  );

  const handleOpen = useCallback(
    (record: DocumentListItem) => {
      router.push(`/editor/${record.id}`);
    },
    [router],
  );

  const handleDelete = useCallback(
    (record: DocumentListItem) => {
      Modal.confirm({
        title: '문서 삭제',
        content: `"${record.original_filename}"을(를) 삭제하시겠습니까?`,
        okText: '삭제',
        okType: 'danger',
        cancelText: '취소',
        async onOk() {
          try {
            await deleteDoc(record.id);
            message.success('문서가 삭제되었습니다.');
          } catch {
            // error already shown by interceptor
          }
        },
      });
    },
    [deleteDoc],
  );

  const columns: ColumnsType<DocumentListItem> = [
    {
      title: '파일명',
      dataIndex: 'original_filename',
      key: 'original_filename',
      render: (text: string) => (
        <Space>
          <FileTextOutlined />
          {text}
        </Space>
      ),
    },
    {
      title: '파일형식',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 100,
      render: (type: string) => (
        <Tag color={fileTypeColorMap[type.toLowerCase()] ?? 'default'}>
          {type.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: '수정일',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (val: string) => new Date(val).toLocaleDateString('ko-KR'),
    },
    {
      title: '액션',
      key: 'action',
      width: 150,
      render: (_: unknown, record: DocumentListItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => handleOpen(record)}
          >
            열기
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          >
            삭제
          </Button>
        </Space>
      ),
    },
  ];

  if (isLoading && documents.length === 0) {
    return <LoadingSpinner tip="문서 목록을 불러오는 중..." />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="문서 목록"
        breadcrumb={[
          { title: '홈', href: '/' },
          { title: '문서 목록' },
        ]}
      />

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card className="dashboard-card">
          <FileUpload
            onUploadComplete={handleUploadComplete}
            acceptTypes={['.hwp', '.hwpx', '.xlsx', '.xls', '.docx', '.doc']}
          />
        </Card>

        {error && (
          <Card>
            <Typography.Text type="danger">{error}</Typography.Text>
          </Card>
        )}

        <Card title="문서 목록" className="dashboard-card">
          <Table<DocumentListItem>
            columns={columns}
            dataSource={documents}
            rowKey="id"
            pagination={{ pageSize: 20 }}
            size="middle"
            loading={isLoading}
          />
        </Card>
      </Space>
    </div>
  );
}
