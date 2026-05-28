'use client';

import React, { useState } from 'react';
import { Layout, Menu } from 'antd';
import {
  HomeOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useRouter, usePathname } from 'next/navigation';

const { Sider } = Layout;

const menuItems = [
  { key: '/', icon: <HomeOutlined />, label: '대시보드' },
  { key: '/documents', icon: <FileTextOutlined />, label: '문서 목록' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const selectedKey =
    menuItems.find((item) => item.key === pathname)?.key ?? '/';

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      theme="light"
      style={{ borderRight: '1px solid #f0f0f0' }}
    >
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={({ key }) => router.push(key)}
        style={{ height: '100%', borderRight: 0 }}
      />
    </Sider>
  );
}
