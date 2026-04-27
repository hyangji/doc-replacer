'use client';

import React, { useEffect, useCallback } from 'react';
import { Typography, Table, Card, Space, Button, Tag, message, Modal, Row, Col, Statistic } from 'antd';
import {
  FileTextOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  UploadOutlined,
  SearchOutlined,
  FileExcelOutlined,
  BookOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useRouter } from 'next/navigation';
import { useDocumentStore } from '@/lib/stores/documentStore';
import type { DocumentListItem } from '@/types/document';
import FileUpload from '@/components/upload/FileUpload';
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

export default function DashboardPage() {
  const router = useRouter();
  const { documents, isLoading, fetchDocuments, deleteDocument: deleteDoc } = useDocumentStore();

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

  const recentDocs = documents.slice(0, 5);

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
      width: 120,
      render: (_: unknown, record: DocumentListItem) => (
        <Space>
          <Button type="link" size="small" icon={<FolderOpenOutlined />} onClick={() => handleOpen(record)}>
            열기
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>
            삭제
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={3}>대시보드</Title>

      {/* 통계 카드 */}
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => router.push('/documents')}>
            <Statistic
              title="전체 문서"
              value={documents.length}
              prefix={<FileTextOutlined />}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => router.push('/documents')}>
            <Statistic
              title="HWP/HWPX 문서"
              value={documents.filter(d => ['hwp', 'hwpx'].includes(d.file_type?.toLowerCase())).length}
              prefix={<FileExcelOutlined />}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => router.push('/law')}>
            <Statistic
              title="법률 검색"
              value="바로가기"
              prefix={<BookOutlined />}
              valueStyle={{ fontSize: 18 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 퀵 액션 */}
      <Card title="빠른 작업">
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={8}>
            <Button
              type="primary"
              icon={<UploadOutlined />}
              size="large"
              block
              onClick={() => router.push('/documents')}
            >
              문서 업로드
            </Button>
          </Col>
          <Col xs={24} sm={8}>
            <Button
              icon={<SearchOutlined />}
              size="large"
              block
              onClick={() => router.push('/law')}
            >
              법률 검색
            </Button>
          </Col>
          <Col xs={24} sm={8}>
            <Button
              icon={<FileTextOutlined />}
              size="large"
              block
              onClick={() => router.push('/documents')}
            >
              문서 목록 보기
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 파일 업로드 */}
      <Card title="파일 업로드">
        <FileUpload
          onUploadComplete={handleUploadComplete}
          acceptTypes={['.hwp', '.hwpx', '.xlsx', '.xls', '.docx', '.doc']}
        />
      </Card>

      {/* 최근 문서 (5건만) */}
      <Card
        title="최근 문서"
        extra={
          documents.length > 5 ? (
            <Button type="link" onClick={() => router.push('/documents')}>
              전체 보기 →
            </Button>
          ) : null
        }
      >
        <Table<DocumentListItem>
          columns={columns}
          dataSource={recentDocs}
          rowKey="id"
          pagination={false}
          size="middle"
          loading={isLoading}
          locale={{ emptyText: '업로드된 문서가 없습니다.' }}
        />
      </Card>
    </Space>
  );
}
