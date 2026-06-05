'use client';

import React, { useState } from 'react';
import { Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';

const { Dragger } = Upload;

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

const DEFAULT_ACCEPT_TYPES = ['.hwp', '.hwpx', '.xlsx', '.xls'];
const DEFAULT_MAX_SIZE = 50 * 1024 * 1024; // 50MB

interface FileUploadProps {
  onUploadComplete?: (file: UploadFile) => void;
  acceptTypes?: string[];
  maxSize?: number;
}

export default function FileUpload({
  onUploadComplete,
  acceptTypes = DEFAULT_ACCEPT_TYPES,
  maxSize = DEFAULT_MAX_SIZE,
}: FileUploadProps) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const acceptString = acceptTypes.join(',');
  const maxSizeMB = Math.round(maxSize / (1024 * 1024));

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    action: `${API_BASE}/api/documents/upload`,
    accept: acceptString,
    fileList,
    beforeUpload(file) {
      const isValidType = acceptTypes.some((type) =>
        file.name.toLowerCase().endsWith(type),
      );
      if (!isValidType) {
        message.error(
          `${file.name}은(는) 지원하지 않는 파일 형식입니다. (${acceptTypes.join(', ')})`,
        );
        return Upload.LIST_IGNORE;
      }

      if (file.size > maxSize) {
        message.error(
          `${file.name}의 크기가 ${maxSizeMB}MB를 초과합니다.`,
        );
        return Upload.LIST_IGNORE;
      }

      return true;
    },
    onChange(info) {
      setFileList(info.fileList);

      if (info.file.status === 'done') {
        message.success(`${info.file.name} 업로드 완료`);
        onUploadComplete?.(info.file);
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} 업로드 실패`);
      }
    },
  };

  return (
    <Dragger {...uploadProps}>
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">
        파일을 드래그하거나 클릭하여 업로드하세요
      </p>
      <p className="ant-upload-hint">
        {acceptTypes.join(', ')} 형식을 지원합니다 (최대 {maxSizeMB}MB)
      </p>
    </Dragger>
  );
}
