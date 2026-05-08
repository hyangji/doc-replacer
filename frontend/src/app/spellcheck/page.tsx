'use client';

import React, { useState, useCallback } from 'react';
import {
  Input, Card, Typography, Button, Empty, Space, Tag, Spin,
  List, Tabs, Badge, Alert,
} from 'antd';
import {
  CheckCircleOutlined, WarningOutlined, EditOutlined, FileSearchOutlined,
} from '@ant-design/icons';
import PageHeader from '@/components/common/PageHeader';
import * as api from '@/lib/api';
import type { SpellError, LegalTermError } from '@/types/spellcheck';

const { Text } = Typography;
const { TextArea } = Input;

type CheckMode = 'spelling' | 'legal';

export default function SpellCheckPage() {
  const [text, setText] = useState('');
  const [checkMode, setCheckMode] = useState<CheckMode>('spelling');
  const [isLoading, setIsLoading] = useState(false);
  const [spellErrors, setSpellErrors] = useState<SpellError[]>([]);
  const [legalErrors, setLegalErrors] = useState<LegalTermError[]>([]);
  const [checked, setChecked] = useState(false);

  const handleCheck = useCallback(async () => {
    if (!text.trim()) return;
    setIsLoading(true);
    setChecked(false);
    try {
      if (checkMode === 'spelling') {
        const result = await api.checkSpelling(text);
        setSpellErrors(result.errors);
        setLegalErrors([]);
      } else {
        const result = await api.checkLegalTerms(text);
        setLegalErrors(result.errors);
        setSpellErrors([]);
      }
      setChecked(true);
    } catch {
      // API 에러는 interceptor에서 처리
    } finally {
      setIsLoading(false);
    }
  }, [text, checkMode]);

  const applySpellFix = (error: SpellError) => {
    const before = text.slice(0, error.position);
    const after = text.slice(error.position + error.original.length);
    setText(before + error.corrected + after);
    setChecked(false);
    setSpellErrors([]);
    setLegalErrors([]);
  };

  const applyLegalFix = (error: LegalTermError) => {
    const before = text.slice(0, error.position);
    const after = text.slice(error.position + error.found.length);
    setText(before + error.suggested + after);
    setChecked(false);
    setSpellErrors([]);
    setLegalErrors([]);
  };

  const totalErrors = checkMode === 'spelling' ? spellErrors.length : legalErrors.length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="맞춤법 검사"
        breadcrumb={[
          { title: '홈', href: '/' },
          { title: '맞춤법 검사' },
        ]}
      />

      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        {/* 좌측: 텍스트 입력 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card size="small" title={<Space><EditOutlined /><Text strong>텍스트 입력</Text></Space>}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Tabs
                activeKey={checkMode}
                onChange={(key) => {
                  setCheckMode(key as CheckMode);
                  setChecked(false);
                  setSpellErrors([]);
                  setLegalErrors([]);
                }}
                items={[
                  { key: 'spelling', label: '맞춤법 검사' },
                  { key: 'legal', label: '법률 용어 검사' },
                ]}
                size="small"
              />
              <TextArea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={
                  checkMode === 'spelling'
                    ? '맞춤법을 검사할 텍스트를 입력하세요...'
                    : '법률 용어 오타를 검사할 텍스트를 입력하세요...'
                }
                autoSize={{ minRows: 15, maxRows: 30 }}
                style={{ fontFamily: 'monospace', fontSize: 14, lineHeight: 1.8 }}
              />
              <Button
                type="primary"
                icon={<FileSearchOutlined />}
                onClick={handleCheck}
                loading={isLoading}
                disabled={!text.trim()}
                block
              >
                {checkMode === 'spelling' ? '맞춤법 검사' : '법률 용어 검사'}
              </Button>
            </Space>
          </Card>
        </div>

        {/* 우측: 검사 결과 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Card
            size="small"
            title={
              <Space>
                <FileSearchOutlined />
                <Text strong>검사 결과</Text>
                {checked && (
                  <Badge
                    count={totalErrors}
                    showZero
                    overflowCount={999}
                    style={{ backgroundColor: totalErrors > 0 ? '#ff4d4f' : '#52c41a' }}
                  />
                )}
              </Space>
            }
            style={{ flex: 1, overflow: 'auto' }}
          >
            {isLoading ? (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Spin tip="검사 중..." />
              </div>
            ) : checked && totalErrors === 0 ? (
              <Alert
                type="success"
                icon={<CheckCircleOutlined />}
                showIcon
                message="오류가 발견되지 않았습니다."
                style={{ margin: 24 }}
              />
            ) : checked && checkMode === 'spelling' ? (
              <List
                dataSource={spellErrors}
                renderItem={(error, idx) => (
                  <List.Item
                    key={idx}
                    actions={[
                      <Button key="fix" size="small" type="link" onClick={() => applySpellFix(error)}>
                        수정 적용
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={<WarningOutlined style={{ color: '#faad14', fontSize: 18 }} />}
                      title={
                        <Space>
                          <Text delete type="danger">{error.original}</Text>
                          <Text>→</Text>
                          <Text strong type="success">{error.corrected}</Text>
                        </Space>
                      }
                      description={
                        <Space>
                          <Tag color={
                            error.type === 'spelling' ? 'red' :
                            error.type === 'spacing' ? 'orange' : 'purple'
                          }>
                            {error.type === 'spelling' ? '맞춤법' :
                             error.type === 'spacing' ? '띄어쓰기' : '문법'}
                          </Tag>
                          <Text type="secondary">위치: {error.position}</Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : checked && checkMode === 'legal' ? (
              <List
                dataSource={legalErrors}
                renderItem={(error, idx) => (
                  <List.Item
                    key={idx}
                    actions={[
                      <Button key="fix" size="small" type="link" onClick={() => applyLegalFix(error)}>
                        수정 적용
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={<WarningOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />}
                      title={
                        <Space>
                          <Text delete type="danger">{error.found}</Text>
                          <Text>→</Text>
                          <Text strong type="success">{error.suggested}</Text>
                        </Space>
                      }
                      description={<Text type="secondary">위치: {error.position}</Text>}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                description="텍스트를 입력하고 검사 버튼을 눌러주세요."
                style={{ padding: 48 }}
              />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
