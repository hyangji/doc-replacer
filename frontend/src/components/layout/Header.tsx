'use client';

import React from 'react';
import { Layout, Menu, Button } from 'antd';
import { SettingOutlined, FileTextOutlined } from '@ant-design/icons';
import { useRouter, usePathname } from 'next/navigation';

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

      <Button
        type="text"
        icon={<SettingOutlined />}
        style={{ marginLeft: 'auto' }}
      />
    </AntHeader>
  );
}
