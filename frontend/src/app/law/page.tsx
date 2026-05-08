'use client';

import React, { useState, useCallback } from 'react';
import {
  Input, Radio, List, Card, Typography, Button, Empty, Space, Tag, Spin,
  Collapse, Alert, Divider,
} from 'antd';
import {
  SearchOutlined, FileTextOutlined, CopyOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import type { RadioChangeEvent } from 'antd';
import PageHeader from '@/components/common/PageHeader';
import { useLawStore } from '@/lib/stores/lawStore';
import type { LawSearchItem } from '@/types/law';

const { Text, Paragraph, Title } = Typography;
const { Search } = Input;

type SearchType = 'name' | 'article' | 'keyword';

const SEARCH_TYPE_MAP: Record<SearchType, string> = {
  name: 'law',
  article: 'jo',
  keyword: 'key',
};

export default function LawPage() {
  const {
    searchResults, totalCount, selectedLaw, lawDetail,
    verifyResult, isLoading,
    searchLaw, selectLaw, verifyLaw,
  } = useLawStore();

  const [searchType, setSearchType] = useState<SearchType>('name');
  const [searchQuery, setSearchQuery] = useState('');

  const handleSearch = useCallback(async (value: string) => {
    if (!value.trim()) return;
    setSearchQuery(value);
    await searchLaw(value, SEARCH_TYPE_MAP[searchType]);
  }, [searchLaw, searchType]);

  const handleSearchTypeChange = (e: RadioChangeEvent) => {
    setSearchType(e.target.value as SearchType);
  };

  const handleSelectLaw = (item: LawSearchItem) => {
    selectLaw(item);
  };

  const handleVerify = useCallback(async () => {
    if (selectedLaw) {
      await verifyLaw(selectedLaw.law_name);
    }
  }, [selectedLaw, verifyLaw]);

  const handleCopyToClipboard = () => {
    if (lawDetail && lawDetail.articles.length > 0) {
      const text = lawDetail.articles
        .map(a => `${a.number} ${a.title}\n${a.content}`)
        .join('\n\n');
      navigator.clipboard.writeText(text);
    } else if (selectedLaw) {
      navigator.clipboard.writeText(selectedLaw.law_name);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="법률 검색"
        breadcrumb={[
          { title: '홈', href: '/' },
          { title: '법률 검색' },
        ]}
      />

      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
        {/* 좌측: 검색 영역 */}
        <div style={{ flex: 6, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card size="small">
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Radio.Group
                value={searchType}
                onChange={handleSearchTypeChange}
                optionType="button"
                buttonStyle="solid"
                size="small"
              >
                <Radio.Button value="name">법령명</Radio.Button>
                <Radio.Button value="article">조문</Radio.Button>
                <Radio.Button value="keyword">키워드</Radio.Button>
              </Radio.Group>

              <Search
                placeholder={
                  searchType === 'name' ? '법령명을 입력하세요 (예: 도시계획법)' :
                  searchType === 'article' ? '조문 번호를 입력하세요 (예: 제1조)' :
                  '키워드를 입력하세요 (예: 도시개발)'
                }
                enterButton="검색"
                size="large"
                prefix={<SearchOutlined />}
                onSearch={handleSearch}
                loading={isLoading}
              />
            </Space>
          </Card>

          <Card
            size="small"
            title={
              <Space>
                <Text strong>검색 결과</Text>
                {totalCount > 0 && <Tag color="blue">{totalCount}건</Tag>}
              </Space>
            }
            style={{ flex: 1, overflow: 'auto' }}
            styles={{ body: { padding: 0 } }}
          >
            {isLoading ? (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Spin tip="검색 중..." />
              </div>
            ) : searchResults.length > 0 ? (
              <List
                dataSource={searchResults}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => handleSelectLaw(item)}
                    style={{
                      cursor: 'pointer',
                      padding: '12px 16px',
                      background: selectedLaw?.law_id === item.law_id ? '#e6f4ff' : 'transparent',
                      borderLeft: selectedLaw?.law_id === item.law_id
                        ? '3px solid #1677ff' : '3px solid transparent',
                    }}
                  >
                    <List.Item.Meta
                      avatar={<FileTextOutlined style={{ fontSize: 20, color: '#1677ff' }} />}
                      title={<Text strong>{item.law_name}</Text>}
                      description={
                        <Space size={4}>
                          {item.law_type && <Tag>{item.law_type}</Tag>}
                          {item.proclamation_date && (
                            <Text type="secondary">공포: {item.proclamation_date}</Text>
                          )}
                          {item.enforcement_date && (
                            <Text type="secondary">시행: {item.enforcement_date}</Text>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                description={searchQuery ? '검색 결과가 없습니다.' : '법령명, 조문, 키워드로 검색해보세요.'}
                style={{ padding: 48 }}
              />
            )}
          </Card>
        </div>

        {/* 우측: 법령 상세 패널 */}
        <div style={{ flex: 4, display: 'flex', flexDirection: 'column' }}>
          <Card
            size="small"
            title={
              selectedLaw ? (
                <Space>
                  <FileTextOutlined />
                  <Text strong>{selectedLaw.law_name}</Text>
                </Space>
              ) : '법령 상세'
            }
            extra={
              selectedLaw && (
                <Space>
                  <Button size="small" icon={<CopyOutlined />} onClick={handleCopyToClipboard}>
                    복사
                  </Button>
                  <Button size="small" onClick={handleVerify}>
                    인용 검증
                  </Button>
                </Space>
              )
            }
            style={{ flex: 1, overflow: 'auto' }}
          >
            {selectedLaw ? (
              <div>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Tag color="blue">{selectedLaw.law_id}</Tag>
                  {selectedLaw.law_type && <Tag color="green">{selectedLaw.law_type}</Tag>}
                  {selectedLaw.proclamation_date && (
                    <Tag>공포: {selectedLaw.proclamation_date}</Tag>
                  )}
                </Space>

                {verifyResult && (
                  <Alert
                    type={verifyResult.exists ? 'success' : 'warning'}
                    showIcon
                    icon={verifyResult.exists ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                    message={verifyResult.exists ? '유효한 법령입니다' : '법령을 찾을 수 없습니다'}
                    description={
                      verifyResult.exists ? (
                        <Space direction="vertical" size={4}>
                          <Text>정확한 법령명: {verifyResult.correct_name}</Text>
                          {verifyResult.last_amended && (
                            <Text>최종 개정: {verifyResult.last_amended}</Text>
                          )}
                          <Text>현행 여부: {verifyResult.is_current ? '현행' : '비현행'}</Text>
                        </Space>
                      ) : undefined
                    }
                    style={{ marginBottom: 12 }}
                  />
                )}

                <Divider style={{ margin: '12px 0' }} />

                {lawDetail && lawDetail.articles.length > 0 ? (
                  <div>
                    <Title level={5}>조문 ({lawDetail.articles.length}개)</Title>
                    <Collapse
                      size="small"
                      items={lawDetail.articles.map((article, idx) => ({
                        key: idx,
                        label: <Text strong>{article.number} {article.title}</Text>,
                        children: (
                          <Paragraph style={{
                            whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 14,
                          }}>
                            {article.content}
                          </Paragraph>
                        ),
                      }))}
                    />
                  </div>
                ) : lawDetail ? (
                  <Empty description="조문 정보가 없습니다." />
                ) : selectedLaw ? (
                  <div style={{ padding: 24, textAlign: 'center' }}>
                    <Spin tip="조문 로딩 중..." />
                  </div>
                ) : null}
              </div>
            ) : (
              <Empty description="좌측에서 법령을 선택하세요." />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
