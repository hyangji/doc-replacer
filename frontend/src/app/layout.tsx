import type { Metadata } from 'next';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import './globals.css';
import RootLayoutClient from './RootLayoutClient';

export const metadata: Metadata = {
  title: 'DocReplacer - 문서 관리 시스템',
  description: '도시계획 제안서의 반복적 문서 수정을 자동화하는 웹 시스템',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        <AntdRegistry>
          <RootLayoutClient>{children}</RootLayoutClient>
        </AntdRegistry>
      </body>
    </html>
  );
}
