'use client';

import React, { useRef, useCallback, useState, useEffect } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import type * as Monaco from 'monaco-editor';
import { Card, Button, Space, Divider, Dropdown, Tooltip, message } from 'antd';
import {
  SaveOutlined,
  UndoOutlined,
  RedoOutlined,
  SwapOutlined,
  FullscreenOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import SearchReplacePanel from './SearchReplacePanel';

interface DocumentEditorProps {
  content?: string;
  onChange?: (content: string) => void;
  language?: string;
  readOnly?: boolean;
  onSave?: (content: string) => void;
  documentId?: string;
}

interface CursorPosition {
  lineNumber: number;
  column: number;
}

const convertMenuItems: MenuProps['items'] = [
  { key: 'docx', label: 'Word (.docx)로 변환' },
  { key: 'pdf', label: 'PDF로 변환' },
];

export default function DocumentEditor({
  content = '',
  onChange,
  language = 'plaintext',
  readOnly = false,
  onSave,
  documentId,
}: DocumentEditorProps) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const [monacoInstance, setMonacoInstance] = useState<typeof Monaco | null>(null);
  const [searchPanelOpen, setSearchPanelOpen] = useState(false);
  const [replaceMode, setReplaceMode] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<CursorPosition>({
    lineNumber: 1,
    column: 1,
  });
  const [totalLines, setTotalLines] = useState(0);
  const [charCount, setCharCount] = useState(0);
  const [matchCount, setMatchCount] = useState(0);
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const decorationsRef = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const updateStats = useCallback((editor: Monaco.editor.IStandaloneCodeEditor) => {
    const model = editor.getModel();
    if (model) {
      setTotalLines(model.getLineCount());
      setCharCount(model.getValue().length);
    }
  }, []);

  const handleEditorMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      setMonacoInstance(monaco);
      updateStats(editor);

      editor.onDidChangeCursorPosition((e) => {
        setCursorPosition({
          lineNumber: e.position.lineNumber,
          column: e.position.column,
        });
      });

      editor.onDidChangeModelContent(() => {
        const val = editor.getValue();
        onChange?.(val);
        updateStats(editor);
      });

      // Ctrl+S: 저장
      editor.addCommand(
        // eslint-disable-next-line no-bitwise
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
        () => {
          onSave?.(editor.getValue());
          message.success('저장되었습니다');
        },
      );

      // Ctrl+F: 검색 패널 열기
      editor.addCommand(
        // eslint-disable-next-line no-bitwise
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyF,
        () => {
          setSearchPanelOpen(true);
          setReplaceMode(false);
        },
      );

      // Ctrl+H: 검색/치환 패널 열기
      editor.addCommand(
        // eslint-disable-next-line no-bitwise
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyH,
        () => {
          setSearchPanelOpen(true);
          setReplaceMode(true);
        },
      );
    },
    [onChange, onSave, updateStats],
  );

  // 툴바 액션
  const handleSave = () => {
    const editor = editorRef.current;
    if (editor) {
      onSave?.(editor.getValue());
      message.success('저장되었습니다');
    }
  };

  const handleUndo = () => {
    editorRef.current?.trigger('toolbar', 'undo', null);
  };

  const handleRedo = () => {
    editorRef.current?.trigger('toolbar', 'redo', null);
  };

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // 검색/치환 로직
  const highlightMatches = useCallback(
    (searchTerm: string, caseSensitive: boolean, useRegex: boolean) => {
      const editor = editorRef.current;
      const monaco = monacoInstance;
      if (!editor || !monaco || !searchTerm) {
        decorationsRef.current?.clear();
        setMatchCount(0);
        setCurrentMatchIndex(0);
        return;
      }

      const model = editor.getModel();
      if (!model) return;

      let matches: Monaco.editor.FindMatch[];
      try {
        matches = model.findMatches(searchTerm, true, useRegex, caseSensitive, null, true);
      } catch {
        decorationsRef.current?.clear();
        setMatchCount(0);
        return;
      }

      setMatchCount(matches.length);

      const decorations = matches.map((match, index) => ({
        range: match.range,
        options: {
          className: index === currentMatchIndex ? 'search-highlight-current' : 'search-highlight',
          overviewRuler: {
            color: index === currentMatchIndex ? '#FFD591' : '#FFFBE6',
            position: monaco.editor.OverviewRulerLane.Center,
          },
        },
      }));

      if (decorationsRef.current) {
        decorationsRef.current.clear();
      }
      decorationsRef.current = editor.createDecorationsCollection(decorations);
    },
    [monacoInstance, currentMatchIndex],
  );

  const navigateMatch = useCallback(
    (direction: 'next' | 'prev', searchTerm: string, caseSensitive: boolean, useRegex: boolean) => {
      const editor = editorRef.current;
      if (!editor || !searchTerm || matchCount === 0) return;

      const model = editor.getModel();
      if (!model) return;

      let matches: Monaco.editor.FindMatch[];
      try {
        matches = model.findMatches(searchTerm, true, useRegex, caseSensitive, null, true);
      } catch {
        return;
      }
      if (matches.length === 0) return;

      const newIndex =
        direction === 'next'
          ? (currentMatchIndex + 1) % matches.length
          : (currentMatchIndex - 1 + matches.length) % matches.length;

      setCurrentMatchIndex(newIndex);
      const match = matches[newIndex];
      editor.revealRangeInCenter(match.range);
      editor.setSelection(match.range);
    },
    [matchCount, currentMatchIndex],
  );

  const handleReplace = useCallback(
    (searchTerm: string, replaceTerm: string, caseSensitive: boolean, useRegex: boolean) => {
      const editor = editorRef.current;
      if (!editor || !searchTerm) return;

      const model = editor.getModel();
      if (!model) return;

      let matches: Monaco.editor.FindMatch[];
      try {
        matches = model.findMatches(searchTerm, true, useRegex, caseSensitive, null, true);
      } catch {
        return;
      }

      if (matches.length === 0 || currentMatchIndex >= matches.length) return;

      const match = matches[currentMatchIndex];
      editor.executeEdits('search-replace', [{ range: match.range, text: replaceTerm }]);
      highlightMatches(searchTerm, caseSensitive, useRegex);
    },
    [currentMatchIndex, highlightMatches],
  );

  const handleReplaceAll = useCallback(
    (searchTerm: string, replaceTerm: string, caseSensitive: boolean, useRegex: boolean) => {
      const editor = editorRef.current;
      if (!editor || !searchTerm) return;

      const model = editor.getModel();
      if (!model) return;

      let matches: Monaco.editor.FindMatch[];
      try {
        matches = model.findMatches(searchTerm, true, useRegex, caseSensitive, null, true);
      } catch {
        return;
      }
      if (matches.length === 0) return;

      const edits = matches.slice().reverse().map((match) => ({ range: match.range, text: replaceTerm }));
      editor.executeEdits('search-replace-all', edits);
      message.success(`${matches.length}개 항목을 바꾸었습니다`);

      decorationsRef.current?.clear();
      setMatchCount(0);
      setCurrentMatchIndex(0);
    },
    [],
  );

  useEffect(() => {
    if (!searchPanelOpen) {
      decorationsRef.current?.clear();
      setMatchCount(0);
      setCurrentMatchIndex(0);
    }
  }, [searchPanelOpen]);

  return (
    <div ref={containerRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Card
        size="small"
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            height: isFullscreen ? '100vh' : '100%',
            padding: 0,
          },
        }}
        style={{ height: '100%', borderRadius: 8 }}
      >
        {/* 상단 툴바 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '6px 12px',
            borderBottom: '1px solid #f0f0f0',
            background: '#fafafa',
          }}
        >
          <Space split={<Divider type="vertical" />}>
            <Space size={4}>
              <Tooltip title="저장 (Ctrl+S)">
                <Button type="text" size="small" icon={<SaveOutlined />} onClick={handleSave} disabled={readOnly}>
                  저장
                </Button>
              </Tooltip>
              <Tooltip title="되돌리기 (Ctrl+Z)">
                <Button type="text" size="small" icon={<UndoOutlined />} onClick={handleUndo} disabled={readOnly} />
              </Tooltip>
              <Tooltip title="다시하기 (Ctrl+Shift+Z)">
                <Button type="text" size="small" icon={<RedoOutlined />} onClick={handleRedo} disabled={readOnly} />
              </Tooltip>
            </Space>

            <Dropdown menu={{ items: convertMenuItems }} placement="bottomLeft">
              <Button type="text" size="small" icon={<SwapOutlined />}>
                변환
              </Button>
            </Dropdown>

            <Space size={4}>
              <Tooltip title="찾기/바꾸기 (Ctrl+H)">
                <Button
                  type="text"
                  size="small"
                  icon={<SearchOutlined />}
                  onClick={() => {
                    setSearchPanelOpen(true);
                    setReplaceMode(true);
                  }}
                />
              </Tooltip>
              <Tooltip title="전체화면">
                <Button type="text" size="small" icon={<FullscreenOutlined />} onClick={handleToggleFullscreen} />
              </Tooltip>
            </Space>
          </Space>
        </div>

        {/* 에디터 영역 */}
        <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
          {searchPanelOpen && (
            <SearchReplacePanel
              showReplace={replaceMode}
              matchCount={matchCount}
              currentMatchIndex={currentMatchIndex}
              onSearch={highlightMatches}
              onNavigate={navigateMatch}
              onReplace={handleReplace}
              onReplaceAll={handleReplaceAll}
              onClose={() => setSearchPanelOpen(false)}
              onToggleReplace={() => setReplaceMode((prev) => !prev)}
            />
          )}

          <Editor
            height="100%"
            defaultLanguage={language}
            defaultValue={content}
            theme="vs-dark"
            onMount={handleEditorMount}
            options={{
              readOnly,
              fontSize: 14,
              fontFamily: "'Pretendard', 'D2Coding', monospace",
              minimap: { enabled: true },
              lineNumbers: 'on',
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              renderWhitespace: 'selection',
              tabSize: 2,
            }}
          />
        </div>

        {/* 하단 상태바 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '3px 12px',
            background: '#007ACC',
            color: '#fff',
            fontSize: 12,
            flexShrink: 0,
          }}
        >
          <span>
            줄 {cursorPosition.lineNumber}, 열 {cursorPosition.column}
          </span>
          <span>
            {documentId && `문서: ${documentId} | `}
            UTF-8 | {totalLines}줄 | {charCount.toLocaleString()}자
            {matchCount > 0 && ` | 검색: ${matchCount}개 일치`}
          </span>
        </div>
      </Card>
    </div>
  );
}
