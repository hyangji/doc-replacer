'use client';

import React, { useState, useCallback } from 'react';
import {
  Input,
  Radio,
  List,
  Card,
  Typography,
  Button,
  Empty,
  Space,
  Tag,
  Spin,
} from 'antd';
import {
  SearchOutlined,
  FileTextOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import type { RadioChangeEvent } from 'antd';
import PageHeader from '@/components/common/PageHeader';
import { useLawStore } from '@/lib/stores/lawStore';
import type { LawSearchItem } from '@/types/law';

const { Text, Paragraph, Title } = Typography;
const { Search } = Input;

type SearchType = 'name' | 'article' | 'keyword';

const MOCK_RESULTS: LawSearchItem[] = [
  {
    law_id: 'LAW-001',
    title: '국토의 계획 및 이용에 관한 법률',
    content_snippet: '제1조(목적) 이 법은 국토의 이용·개발과 보전을 위한 계획의 수립 및 집행 등에 관하여 필요한 사항을 정하여 공공복리의 증진과 국민의 삶의 질 향상에 이바지함을 목적으로 한다.',
  },
  {
    law_id: 'LAW-002',
    title: '도시개발법',
    content_snippet: '제1조(목적) 이 법은 도시개발에 필요한 사항을 규정하여 계획적이고 체계적인 도시개발을 도모하고 쾌적한 도시환경의 조성과 공공복리의 증진에 이바지함을 목적으로 한다.',
  },
  {
    law_id: 'LAW-003',
    title: '도시 및 주거환경정비법',
    content_snippet: '제1조(목적) 이 법은 도시기능의 회복이 필요하거나 주거환경이 불량한 지역을 계획적으로 정비하고 노후·불량건축물을 효율적으로 개량하기 위하여 필요한 사항을 규정함으로써 도시환경을 개선하고 주거생활의 질을 높이는 데 이바지함을 목적으로 한다.',
  },
  {
    law_id: 'LAW-004',
    title: '건축법',
    content_snippet: '제1조(목적) 이 법은 건축물의 대지·구조·설비 기준 및 용도 등을 정하여 건축물의 안전·기능·환경 및 미관을 향상시킴으로써 공공복리의 증진에 이바지함을 목적으로 한다.',
  },
  {
    law_id: 'LAW-005',
    title: '주택법',
    content_snippet: '제1조(목적) 이 법은 주택의 건설·공급 및 주택시장의 관리 등에 관한 사항을 정함으로써 국민의 주거안정과 주거수준의 향상에 이바지함을 목적으로 한다.',
  },
];

export default function LawPage() {
  const {
    searchResults,
    totalCount,
    selectedLaw,
    isLoading,
    searchLaw,
    selectLaw,
  } = useLawStore();

  const [searchType, setSearchType] = useState<SearchType>('name');
  const [searchQuery, setSearchQuery] = useState('');
  const [useMock, setUseMock] = useState(false);

  const displayResults = useMock ? MOCK_RESULTS : searchResults;
  const displaySelected = useMock
    ? (selectedLaw ?? MOCK_RESULTS[0])
    : selectedLaw;

  const handleSearch = useCallback(
    async (value: string) => {
      if (!value.trim()) return;
      setSearchQuery(value);
      try {
        await searchLaw(value);
        setUseMock(false);
      } catch {
        // API 미구현 시 mock 데이터로 폴백
        setUseMock(true);
        selectLaw(MOCK_RESULTS[0]);
      }
    },
    [searchLaw, selectLaw],
  );

  const handleSearchTypeChange = (e: RadioChangeEvent) => {
    setSearchType(e.target.value as SearchType);
  };

  const handleSelectLaw = (item: LawSearchItem) => {
    selectLaw(item);
  };

  const handleCopyToClipboard = () => {
    if (displaySelected) {
      navigator.clipboard.writeText(displaySelected.content_snippet);
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
        {/* 좌측: 검색 영역 (60%) */}
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
                  searchType === 'name'
                    ? '법령명을 입력하세요 (예: 도시계획법)'
                    : searchType === 'article'
                      ? '조문 번호를 입력하세요 (예: 제1조)'
                      : '키워드를 입력하세요 (예: 도시개발)'
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
                {(displayResults.length > 0 || totalCount > 0) && (
                  <Tag color="blue">
                    {useMock ? displayResults.length : totalCount}건
                  </Tag>
                )}
              </Space>
            }
            style={{ flex: 1, overflow: 'auto' }}
            styles={{ body: { padding: 0 } }}
          >
            {isLoading ? (
              <div style={{ padding: 48, textAlign: 'center' }}>
                <Spin tip="검색 중..." />
              </div>
            ) : displayResults.length > 0 ? (
              <List
                dataSource={displayResults}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => handleSelectLaw(item)}
                    style={{
                      cursor: 'pointer',
                      padding: '12px 16px',
                      background:
                        displaySelected?.law_id === item.law_id
                          ? '#e6f4ff'
                          : 'transparent',
                      borderLeft:
                        displaySelected?.law_id === item.law_id
                          ? '3px solid #1677ff'
                          : '3px solid transparent',
                    }}
                  >
                    <List.Item.Meta
                      avatar={<FileTextOutlined style={{ fontSize: 20, color: '#1677ff' }} />}
                      title={
                        <Text strong>{item.title}</Text>
                      }
                      description={
                        <Paragraph
                          ellipsis={{ rows: 2 }}
                          style={{ marginBottom: 0, color: '#666' }}
                        >
                          {item.content_snippet}
                        </Paragraph>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                description={
                  searchQuery
                    ? '검색 결과가 없습니다.'
                    : '법령명, 조문, 키워드로 검색해보세요.'
                }
                style={{ padding: 48 }}
              />
            )}
          </Card>
        </div>

        {/* 우측: 조문 상세 패널 (40%) */}
        <div style={{ flex: 4, display: 'flex', flexDirection: 'column' }}>
          <Card
            size="small"
            title={
              displaySelected ? (
                <Space>
                  <FileTextOutlined />
                  <Text strong>{displaySelected.title}</Text>
                </Space>
              ) : (
                '조문 상세'
              )
            }
            extra={
              displaySelected && (
                <Space>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={handleCopyToClipboard}
                  >
                    복사
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    disabled
                  >
                    문서에 삽입
                  </Button>
                </Space>
              )
            }
            style={{ flex: 1, overflow: 'auto' }}
          >
            {displaySelected ? (
              <div>
                <Tag color="blue" style={{ marginBottom: 12 }}>
                  {displaySelected.law_id}
                </Tag>
                <Title level={5}>{displaySelected.title}</Title>
                <Paragraph
                  style={{
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.8,
                    fontSize: 14,
                    background: '#fafafa',
                    padding: 16,
                    borderRadius: 8,
                    border: '1px solid #f0f0f0',
                  }}
                >
                  {displaySelected.content_snippet}
                </Paragraph>
              </div>
            ) : (
              <Empty description="좌측에서 법률을 선택하세요." />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
