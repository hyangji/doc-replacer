'use client';

import React, { useState } from 'react';
import { Upload, message, Result, Alert } from 'antd';
import { FileExcelOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';

const { Dragger } = Upload;

const MAX_SIZE = 50 * 1024 * 1024; // 50MB

interface ReplacementResponse {
  document_id: number;
  replaced_count: number;
  version_number: number;
}

interface ExcelUploadProps {
  onUploadComplete?: () => void;
  documentId?: string;
}

export default function ExcelUpload({
  onUploadComplete,
  documentId,
}: ExcelUploadProps) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [result, setResult] = useState<ReplacementResponse | null>(null);

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

      // Reset previous result when uploading a new file
      setResult(null);
      return true;
    },
    onChange(info) {
      setFileList(info.fileList);

      if (info.file.status === 'done') {
        const response = info.file.response as ReplacementResponse | undefined;
        if (response) {
          setResult(response);
          if (response.replaced_count > 0) {
            message.success(
              `${response.replaced_count}건 교체 완료 (버전 ${response.version_number})`,
            );
            onUploadComplete?.();
          } else {
            message.warning('일치하는 내용이 없습니다.');
          }
        }
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} 업로드 실패`);
        setResult(null);
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

      {result !== null && result.replaced_count > 0 && (
        <Result
          status="success"
          icon={<CheckCircleOutlined />}
          title={`${result.replaced_count}건 교체 완료`}
          subTitle={`문서 ID: ${result.document_id} / 버전: ${result.version_number}`}
        />
      )}

      {result !== null && result.replaced_count === 0 && (
        <Alert
          type="warning"
          showIcon
          message="교체된 내용 없음"
          description="엑셀 파일에 일치하는 교체 대상이 없습니다. 파일 내용을 확인해주세요."
        />
      )}
    </div>
  );
}
