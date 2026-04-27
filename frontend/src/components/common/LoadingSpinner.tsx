'use client';

import React from 'react';
import { Spin } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

interface LoadingSpinnerProps {
  tip?: string;
}

export default function LoadingSpinner({
  tip = '로딩 중...',
}: LoadingSpinnerProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '60vh',
      }}
    >
      <Spin
        indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />}
        tip={tip}
        size="large"
      >
        <div style={{ padding: 50 }} />
      </Spin>
    </div>
  );
}
