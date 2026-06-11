'use client';

// React 19에서 antd v5 정적 메서드(message/Modal.confirm/notification)가 동작하도록 패치.
// (React 19가 ReactDOM.render를 제거 → 패치 없으면 정적 메서드가 조용히 실패)
import '@ant-design/v5-patch-for-react-19';
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
