'use client';

import React from 'react';
import { ConfigProvider, Layout } from 'antd';
import koKR from 'antd/locale/ko_KR';
import Header from '@/components/layout/Header';
import Sidebar from '@/components/layout/Sidebar';

const { Content } = Layout;

export default function RootLayoutClient({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ConfigProvider
      locale={koKR}
      theme={{
        token: {
          fontFamily:
            "'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Header />
        <Layout>
          <Sidebar />
          <Content style={{ padding: 24, background: '#f5f5f5' }}>
            {children}
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
