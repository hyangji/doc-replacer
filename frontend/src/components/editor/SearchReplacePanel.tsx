'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Input, Button, Tooltip, Space, Typography } from 'antd';
import type { InputRef } from 'antd';
import {
  CloseOutlined,
  UpOutlined,
  DownOutlined,
  SwapOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

interface SearchReplacePanelProps {
  showReplace: boolean;
  matchCount: number;
  currentMatchIndex: number;
  onSearch: (searchTerm: string, caseSensitive: boolean, useRegex: boolean) => void;
  onNavigate: (
    direction: 'next' | 'prev',
    searchTerm: string,
    caseSensitive: boolean,
    useRegex: boolean,
  ) => void;
  onReplace: (
    searchTerm: string,
    replaceTerm: string,
    caseSensitive: boolean,
    useRegex: boolean,
  ) => void;
  onReplaceAll: (
    searchTerm: string,
    replaceTerm: string,
    caseSensitive: boolean,
    useRegex: boolean,
  ) => void;
  onClose: () => void;
  onToggleReplace: () => void;
}

export default function SearchReplacePanel({
  showReplace,
  matchCount,
  currentMatchIndex,
  onSearch,
  onNavigate,
  onReplace,
  onReplaceAll,
  onClose,
  onToggleReplace,
}: SearchReplacePanelProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [replaceTerm, setReplaceTerm] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [useRegex, setUseRegex] = useState(false);

  const searchInputRef = useRef<InputRef>(null);

  useEffect(() => {
    // 패널 열릴 때 검색 입력란에 포커스
    searchInputRef.current?.focus();
  }, []);

  const triggerSearch = useCallback(
    (term: string, cs: boolean, regex: boolean) => {
      onSearch(term, cs, regex);
    },
    [onSearch],
  );

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchTerm(value);
    triggerSearch(value, caseSensitive, useRegex);
  };

  const toggleCaseSensitive = () => {
    const next = !caseSensitive;
    setCaseSensitive(next);
    triggerSearch(searchTerm, next, useRegex);
  };

  const toggleRegex = () => {
    const next = !useRegex;
    setUseRegex(next);
    triggerSearch(searchTerm, caseSensitive, next);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const direction = e.shiftKey ? 'prev' : 'next';
      onNavigate(direction, searchTerm, caseSensitive, useRegex);
    }
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const handleReplaceKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onReplace(searchTerm, replaceTerm, caseSensitive, useRegex);
    }
    if (e.key === 'Escape') {
      onClose();
    }
  };

  const toggleButtonStyle = (active: boolean): React.CSSProperties => ({
    fontWeight: active ? 700 : 400,
    background: active ? 'rgba(255,255,255,0.15)' : 'transparent',
    color: '#fff',
    border: active ? '1px solid rgba(255,255,255,0.4)' : '1px solid transparent',
  });

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 20,
        zIndex: 10,
        background: '#252526',
        border: '1px solid #3C3C3C',
        borderRadius: '0 0 6px 6px',
        padding: '8px 12px',
        minWidth: 360,
        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
      }}
    >
      {/* 검색 행 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          marginBottom: showReplace ? 6 : 0,
        }}
      >
        <Tooltip title={showReplace ? '바꾸기 닫기' : '바꾸기 열기'}>
          <Button
            type="text"
            size="small"
            icon={<SwapOutlined />}
            onClick={onToggleReplace}
            style={{ color: '#CCCCCC' }}
          />
        </Tooltip>

        <Input
          ref={searchInputRef}
          placeholder="찾기"
          size="small"
          value={searchTerm}
          onChange={handleSearchChange}
          onKeyDown={handleSearchKeyDown}
          style={{
            flex: 1,
            background: '#3C3C3C',
            borderColor: '#3C3C3C',
            color: '#CCCCCC',
          }}
        />

        <Tooltip title="대소문자 구분 (Aa)">
          <Button
            type="text"
            size="small"
            onClick={toggleCaseSensitive}
            style={toggleButtonStyle(caseSensitive)}
          >
            Aa
          </Button>
        </Tooltip>

        <Tooltip title="정규식 (.*)">
          <Button
            type="text"
            size="small"
            onClick={toggleRegex}
            style={toggleButtonStyle(useRegex)}
          >
            .*
          </Button>
        </Tooltip>

        <Text
          style={{
            color: '#AAAAAA',
            fontSize: 12,
            whiteSpace: 'nowrap',
            minWidth: 70,
            textAlign: 'center',
          }}
        >
          {matchCount > 0
            ? `${currentMatchIndex + 1}/${matchCount}`
            : searchTerm
              ? '결과 없음'
              : ''}
        </Text>

        <Space size={0}>
          <Tooltip title="이전 결과 (Shift+Enter)">
            <Button
              type="text"
              size="small"
              icon={<UpOutlined />}
              disabled={matchCount === 0}
              onClick={() =>
                onNavigate('prev', searchTerm, caseSensitive, useRegex)
              }
              style={{ color: '#CCCCCC' }}
            />
          </Tooltip>
          <Tooltip title="다음 결과 (Enter)">
            <Button
              type="text"
              size="small"
              icon={<DownOutlined />}
              disabled={matchCount === 0}
              onClick={() =>
                onNavigate('next', searchTerm, caseSensitive, useRegex)
              }
              style={{ color: '#CCCCCC' }}
            />
          </Tooltip>
          <Tooltip title="닫기 (Esc)">
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={onClose}
              style={{ color: '#CCCCCC' }}
            />
          </Tooltip>
        </Space>
      </div>

      {/* 바꾸기 행 */}
      {showReplace && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div style={{ width: 24 }} />

          <Input
            placeholder="바꾸기"
            size="small"
            value={replaceTerm}
            onChange={(e) => setReplaceTerm(e.target.value)}
            onKeyDown={handleReplaceKeyDown}
            style={{
              flex: 1,
              background: '#3C3C3C',
              borderColor: '#3C3C3C',
              color: '#CCCCCC',
            }}
          />

          <Button
            size="small"
            disabled={matchCount === 0}
            onClick={() =>
              onReplace(searchTerm, replaceTerm, caseSensitive, useRegex)
            }
            style={{
              background: '#3C3C3C',
              borderColor: '#3C3C3C',
              color: '#CCCCCC',
            }}
          >
            바꾸기
          </Button>

          <Button
            size="small"
            disabled={matchCount === 0}
            onClick={() =>
              onReplaceAll(searchTerm, replaceTerm, caseSensitive, useRegex)
            }
            style={{
              background: '#3C3C3C',
              borderColor: '#3C3C3C',
              color: '#CCCCCC',
            }}
          >
            모두 바꾸기
          </Button>
        </div>
      )}
    </div>
  );
}
