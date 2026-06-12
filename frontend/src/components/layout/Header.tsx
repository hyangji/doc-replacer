'use client';

import React from 'react';
import { Layout, Menu, Button } from 'antd';
import { QuestionCircleOutlined, FileTextOutlined } from '@ant-design/icons';
import { useRouter, usePathname } from 'next/navigation';

// 편집기 페이지에서 헤더의 '사용 가이드' 버튼 → 편집기로 가이드 시작 신호 전달용 이벤트명
export const OPEN_GUIDE_EVENT = 'docreplacer:open-guide';

const { Header: AntHeader } = Layout;

const menuItems = [
  { key: '/documents', label: '문서 작업', icon: <FileTextOutlined /> },
];

export default function Header() {
  const router = useRouter();
  const pathname = usePathname();

  const selectedKey = menuItems.find((item) => item.key === pathname)?.key ?? '/documents';

  return (
    <AntHeader
      style={{
        display: 'flex',
        alignItems: 'center',
        background: '#fff',
        borderBottom: '1px solid #f0f0f0',
        padding: '0 24px',
      }}
    >
      <div
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: '#1677ff',
          marginRight: 40,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
        onClick={() => router.push('/documents')}
      >
        DocReplacer
      </div>

      <Menu
        mode="horizontal"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={({ key }) => router.push(key)}
        style={{ flex: 1, borderBottom: 'none' }}
      />

      {/* 문서 작업·편집기 화면에서 '사용 가이드' 버튼 노출. 클릭 시 커스텀 이벤트 발신 → 해당 페이지가 수신해 투어 시작 */}
      {(pathname === '/documents' || pathname.startsWith('/editor')) && (
        <Button
          type="primary"
          icon={<QuestionCircleOutlined />}
          style={{ marginLeft: 'auto', background: '#722ed1', borderColor: '#722ed1' }}
          onClick={() => window.dispatchEvent(new CustomEvent(OPEN_GUIDE_EVENT))}
        >
          사용 가이드
        </Button>
      )}
    </AntHeader>
  );
}
