'use client';

import React, { useState } from 'react';
import { Upload, message, Table, Card, Empty } from 'antd';
import { FileExcelOutlined } from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

const { Dragger } = Upload;

const MAX_SIZE = 50 * 1024 * 1024; // 50MB

interface MappingRow {
  key: string;
  column: string;
  sample: string;
  mapped: string;
}

interface ExcelPreviewData {
  columns: MappingRow[];
}

interface ExcelUploadProps {
  onUploadComplete?: (data: ExcelPreviewData) => void;
  documentId?: string;
}

const previewColumns: ColumnsType<MappingRow> = [
  {
    title: '엑셀 컬럼',
    dataIndex: 'column',
    key: 'column',
  },
  {
    title: '샘플 데이터',
    dataIndex: 'sample',
    key: 'sample',
  },
  {
    title: '매핑 대상',
    dataIndex: 'mapped',
    key: 'mapped',
  },
];

export default function ExcelUpload({
  onUploadComplete,
  documentId,
}: ExcelUploadProps) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [previewData, setPreviewData] = useState<MappingRow[]>([]);

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    action: documentId
      ? `/api/documents/${documentId}/excel-upload`
      : '/api/documents/excel-upload',
    accept: '.xlsx,.xls',
    fileList,
    maxCount: 1,
    beforeUpload(file) {
      const isExcel =
        file.name.toLowerCase().endsWith('.xlsx') ||
        file.name.toLowerCase().endsWith('.xls');
      if (!isExcel) {
        message.error('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
        return Upload.LIST_IGNORE;
      }

      if (file.size > MAX_SIZE) {
        message.error('파일 크기가 50MB를 초과합니다.');
        return Upload.LIST_IGNORE;
      }

      return true;
    },
    onChange(info) {
      setFileList(info.fileList);

      if (info.file.status === 'done') {
        message.success(`${info.file.name} 업로드 완료`);

        const response = info.file.response as ExcelPreviewData | undefined;
        if (response?.columns) {
          setPreviewData(response.columns);
          onUploadComplete?.(response);
        }
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} 업로드 실패`);
      }
    },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Dragger {...uploadProps}>
        <p className="ant-upload-drag-icon">
          <FileExcelOutlined />
        </p>
        <p className="ant-upload-text">
          엑셀 파일을 드래그하거나 클릭하여 업로드하세요
        </p>
        <p className="ant-upload-hint">XLSX, XLS 형식을 지원합니다</p>
      </Dragger>

      {previewData.length > 0 ? (
        <Card title="매핑 미리보기" size="small">
          <Table<MappingRow>
            columns={previewColumns}
            dataSource={previewData}
            pagination={false}
            size="small"
          />
        </Card>
      ) : (
        fileList.length > 0 &&
        fileList[0].status === 'done' && (
          <Empty description="매핑 데이터가 없습니다" />
        )
      )}
    </div>
  );
}
