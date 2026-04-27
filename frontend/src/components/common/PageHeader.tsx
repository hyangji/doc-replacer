'use client';

import React from 'react';
import { Breadcrumb, Typography, Space } from 'antd';
import type { BreadcrumbProps } from 'antd';

const { Title } = Typography;

interface PageHeaderProps {
  title: string;
  breadcrumb?: BreadcrumbProps['items'];
  actions?: React.ReactNode;
}

export default function PageHeader({
  title,
  breadcrumb,
  actions,
}: PageHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 24,
      }}
    >
      <div>
        {breadcrumb && breadcrumb.length > 0 && (
          <Breadcrumb
            items={breadcrumb}
            style={{ marginBottom: 8 }}
          />
        )}
        <Title level={3} style={{ margin: 0 }}>
          {title}
        </Title>
      </div>

      {actions && <Space>{actions}</Space>}
    </div>
  );
}
