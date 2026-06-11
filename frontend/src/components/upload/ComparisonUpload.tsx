'use client';

import React, { useState, useMemo } from 'react';
import {
  Upload,
  message,
  Alert,
  Button,
  Table,
  Tag,
  Space,
  Typography,
  Divider,
  Tooltip,
  Collapse,
  Modal,
} from 'antd';
import {
  FileExcelOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type {
  ComparisonChangeItem,
  ComparisonSectionInfo,
  ReplacementItem,
} from '@/types/document';
import * as api from '@/lib/api';

const { Dragger } = Upload;
const { Text } = Typography;

const MAX_SIZE = 50 * 1024 * 1024; // 50MB

interface ComparisonUploadProps {
  documentId: string;
  onApplyComplete?: () => void;
  /** 이미 적용/편집 중인 비교 작업이 있는지(있으면 재적용 시 경고) */
  hasExistingWork?: boolean;
}

// 중복 제거용 키. 같은 값이라도 항목(field_name)이 다르면 사용자에겐 다른 항목이므로
// field_name 까지 포함해 분리한다. (적용 시 동일 old→new 중복 교체는 applyReplacements가 처리)
function dedupeKey(item: ComparisonChangeItem): string {
  return `${item.field_name}|||${item.old_value}|||${item.new_value}`;
}

// 안전 여부 판단: 매칭 1건이면 안전(자동 체크). 초록 "안전" 태그와 일치.
function isSafe(item: ComparisonChangeItem): boolean {
  return item.match_count === 1;
}

// 표 행 타입 (dedup 후)
interface RowData extends ComparisonChangeItem {
  rowKey: string;
  sheets: string[]; // 등장한 시트 목록 (sheet 가 대표 시트)
}

// 시트(표) 단위 그룹
interface SheetGroup {
  sheet: string;
  rows: RowData[];
}

export default function ComparisonUpload({
  documentId,
  onApplyComplete,
  hasExistingWork = false,
}: ComparisonUploadProps) {
  const [previewLoading, setPreviewLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [rows, setRows] = useState<RowData[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [fileName, setFileName] = useState<string>('');
  const [totalChanges, setTotalChanges] = useState(0);
  const [unmatchedCount, setUnmatchedCount] = useState(0);
  const [sections, setSections] = useState<ComparisonSectionInfo[]>([]);

  // dedup 처리 + 기본 선택 계산
  function buildRows(items: ComparisonChangeItem[]): { deduped: RowData[]; defaultKeys: React.Key[] } {
    const map = new Map<string, RowData>();
    for (const item of items) {
      const key = dedupeKey(item);
      if (map.has(key)) {
        const existing = map.get(key)!;
        if (!existing.sheets.includes(item.sheet)) {
          existing.sheets.push(item.sheet);
        }
      } else {
        map.set(key, { ...item, rowKey: key, sheets: [item.sheet] });
      }
    }
    const deduped = Array.from(map.values());
    const defaultKeys = deduped
      .filter((r) => isSafe(r))
      .map((r) => r.rowKey);
    return { deduped, defaultKeys };
  }

  async function handleFile(file: File): Promise<boolean> {
    const isExcel =
      file.name.toLowerCase().endsWith('.xlsx') ||
      file.name.toLowerCase().endsWith('.xls');
    if (!isExcel) {
      message.error('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
      return false;
    }
    if (file.size > MAX_SIZE) {
      message.error('파일 크기가 50MB를 초과합니다.');
      return false;
    }

    setFileName(file.name);
    setPreviewLoading(true);
    setRows([]);
    setSelectedKeys([]);
    setSections([]);

    try {
      const response = await api.previewComparison(Number(documentId), file);

      // 전체 changes 펼치기
      const allChanges: ComparisonChangeItem[] = [];
      for (const sheet of response.sheets) {
        for (const change of sheet.changes) {
          allChanges.push({ ...change, sheet: sheet.name });
        }
      }

      const { deduped, defaultKeys } = buildRows(allChanges);
      setRows(deduped);
      setSelectedKeys(defaultKeys);
      setTotalChanges(response.total_changes);
      setUnmatchedCount(response.unmatched_count);
      setSections(response.sections ?? []);

      if (deduped.length === 0) {
        message.warning('변경 후보가 없습니다. 대비표 파일을 확인하세요.');
      } else {
        message.success(
          `미리보기 완료: 총 ${response.total_changes}건 후보 (중복 제거 후 ${deduped.length}건)`,
        );
      }
    } catch {
      // 에러는 api 인터셉터에서 처리
    } finally {
      setPreviewLoading(false);
    }

    return false; // antd Upload의 자동 업로드 막기
  }

  function handleApply() {
    if (selectedKeys.length === 0) {
      message.warning('적용할 항목을 선택하세요.');
      return;
    }

    // 재적용(이미 적용/편집 중인 작업 존재)인 경우에만 경고 모달.
    // 처음 적용에는 경고 없이 바로 진행.
    if (hasExistingWork) {
      Modal.confirm({
        title: '새 엑셀로 다시 적용할까요?',
        content:
          '새 엑셀을 적용하면 원본 기준으로 다시 비교하며, 현재 적용·편집한 내용은 초기화됩니다. 계속할까요?',
        okText: '예, 새로 적용',
        cancelText: '아니오',
        okButtonProps: { danger: true },
        onOk: () => doApply(),
      });
      return;
    }

    void doApply();
  }

  async function doApply() {
    const selectedRows = rows.filter((r) => selectedKeys.includes(r.rowKey));
    const replacements: ReplacementItem[] = selectedRows.map((r) => ({
      field_name: r.field_name,
      old_value: r.old_value,
      new_value: r.new_value,
    }));

    setApplyLoading(true);
    try {
      const result = await api.applyReplacements(Number(documentId), replacements);
      if (result.replaced_count > 0) {
        message.success(
          `${result.replaced_count}건 교체 완료 (버전 ${result.version_number}). Diff 탭에서 확인하세요.`,
        );
        onApplyComplete?.();
      } else {
        message.warning('교체된 내용이 없습니다. 문서와 대비표 내용을 확인하세요.');
      }
    } catch {
      // 에러는 api 인터셉터에서 처리
    } finally {
      setApplyLoading(false);
    }
  }

  function renderMatchTag(matchCount: number) {
    if (matchCount === 0) {
      return (
        <Tag
          color="red"
          icon={<ExclamationCircleOutlined />}
          style={{ cursor: 'default' }}
        >
          매칭없음
        </Tag>
      );
    }
    if (matchCount === 1) {
      return (
        <Tag color="green" icon={<CheckCircleOutlined />}>
          안전
        </Tag>
      );
    }
    return (
      <Tooltip title="전역 교체이므로 문서의 다른 위치도 함께 바뀔 수 있습니다. 직접 확인 후 선택하세요.">
        <Tag
          color="orange"
          icon={<WarningOutlined />}
          style={{ cursor: 'help' }}
          onClick={(e) => e.stopPropagation()}
        >
          주의 {matchCount}건
        </Tag>
      </Tooltip>
    );
  }

  function renderSectionBadge(section: ComparisonSectionInfo) {
    if (section.status === 'parsed') {
      return (
        <Tag color="green" icon={<CheckCircleOutlined />}>
          추출 {section.extracted_count}건
        </Tag>
      );
    }
    if (section.status === 'empty') {
      return (
        <Tag color="orange" icon={<WarningOutlined />}>
          확인 필요
        </Tag>
      );
    }
    return (
      <Tag color="default" style={{ color: '#8c8c8c' }}>
        건너뜀(면적 외)
      </Tag>
    );
  }

  // 시트별로 구간을 묶어 표시 (입력 순서 유지)
  const sectionGroups = useMemo(() => {
    const groups: { sheet: string; items: ComparisonSectionInfo[] }[] = [];
    const indexBySheet = new Map<string, number>();
    for (const section of sections) {
      let idx = indexBySheet.get(section.sheet);
      if (idx === undefined) {
        idx = groups.length;
        indexBySheet.set(section.sheet, idx);
        groups.push({ sheet: section.sheet, items: [] });
      }
      groups[idx].items.push(section);
    }
    return groups;
  }, [sections]);

  const hasUncertainSection = useMemo(
    () => sections.some((s) => s.status === 'empty' || s.status === 'skipped'),
    [sections],
  );

  // 변경 목록을 표(sheet) 단위로 그룹핑 (입력 순서 유지)
  const sheetGroups = useMemo<SheetGroup[]>(() => {
    const groups: SheetGroup[] = [];
    const indexBySheet = new Map<string, number>();
    for (const row of rows) {
      let idx = indexBySheet.get(row.sheet);
      if (idx === undefined) {
        idx = groups.length;
        indexBySheet.set(row.sheet, idx);
        groups.push({ sheet: row.sheet, rows: [] });
      }
      groups[idx].rows.push(row);
    }
    return groups;
  }, [rows]);

  const columns: ColumnsType<RowData> = [
    {
      title: '항목',
      dataIndex: 'field_name',
      key: 'field_name',
      // 맥락이 핵심이므로 잘리지 않게 줄바꿈 허용 + 충분한 폭
      render: (text: string) => (
        <Text style={{ fontSize: 13, whiteSpace: 'normal', wordBreak: 'break-word' }}>
          {text || <Text type="secondary">(항목명 없음)</Text>}
        </Text>
      ),
    },
    {
      title: '값 변경',
      key: 'value_change',
      width: 320,
      render: (_: unknown, record: RowData) => (
        <Space size={6} wrap={false} style={{ alignItems: 'center' }}>
          <Text style={{ fontFamily: 'monospace', fontSize: 13 }}>
            {record.old_value}
          </Text>
          <Text type="secondary">→</Text>
          <Text
            style={{ fontFamily: 'monospace', fontSize: 13, color: '#237804' }}
            strong
          >
            {record.new_value}
          </Text>
        </Space>
      ),
    },
    {
      title: '매칭수',
      dataIndex: 'match_count',
      key: 'match_count',
      width: 110,
      render: (count: number) => renderMatchTag(count),
    },
  ];

  // 요약 수치
  const selectedCount = selectedKeys.length;
  const totalRows = rows.length;
  const unmatchedRows = rows.filter((r) => r.match_count === 0).length;

  // match_count === 0 인 행은 체크 불가
  // preserveSelectedRowKeys: 시트별로 표가 여러 개라 한 rowSelection을 공유하는데,
  // 이 옵션이 없으면 다른 표를 체크할 때 현재 표에 없는 키(=다른 표 선택분)가 유실됨.
  const rowSelection = useMemo(
    () => ({
      selectedRowKeys: selectedKeys,
      preserveSelectedRowKeys: true,
      onChange: (keys: React.Key[]) => setSelectedKeys(keys),
      getCheckboxProps: (record: RowData) => ({
        disabled: record.match_count === 0,
        title:
          record.match_count === 0
            ? '문서에서 해당 값이 발견되지 않아 선택할 수 없습니다.'
            : undefined,
      }),
    }),
    [selectedKeys],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 안내 Alert */}
      <Alert
        type="info"
        showIcon
        message="대비표 기반 HWP 표 일괄 수정"
        description="콤마 포함 면적 값(예: 184,636)은 안전합니다. 매칭수가 2 이상이거나 짧은 숫자(구성비 등)는 문서의 다른 위치도 함께 바뀔 수 있으니 직접 확인 후 선택하세요."
      />

      {/* 파일 업로드 영역 */}
      <Dragger
        name="file"
        multiple={false}
        accept=".xlsx,.xls"
        showUploadList={false}
        beforeUpload={handleFile}
        disabled={previewLoading}
      >
        <p className="ant-upload-drag-icon">
          <FileExcelOutlined style={{ fontSize: 32, color: '#1677ff' }} />
        </p>
        <p className="ant-upload-text">
          대비표 엑셀 파일을 드래그하거나 클릭하여 업로드하세요
        </p>
        <p className="ant-upload-hint">
          {fileName
            ? `선택된 파일: ${fileName}`
            : 'XLSX 형식 지원 — 업로드 시 자동으로 변경 목록을 미리봅니다'}
        </p>
      </Dragger>

      {/* 미리보기 결과 */}
      {rows.length > 0 && (
        <>
          <Divider style={{ margin: '4px 0' }} />

          {/* 요약 */}
          <div
            style={{
              display: 'flex',
              gap: 24,
              alignItems: 'center',
              padding: '8px 4px',
            }}
          >
            <Text>
              전체 후보:{' '}
              <Text strong>{totalChanges}건</Text>
              {totalRows !== totalChanges && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {' '}
                  (중복 제거 후 {totalRows}건)
                </Text>
              )}
            </Text>
            <Text>
              선택:{' '}
              <Text strong style={{ color: '#1677ff' }}>
                {selectedCount}건
              </Text>
            </Text>
            {unmatchedRows > 0 && (
              <Text>
                매칭없음:{' '}
                <Text strong style={{ color: '#ff4d4f' }}>
                  {unmatchedRows}건
                </Text>
              </Text>
            )}
            {unmatchedCount > 0 && unmatchedRows === 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                (미매칭 {unmatchedCount}건 포함)
              </Text>
            )}
          </div>

          {/* 구간 처리 현황 */}
          {sections.length > 0 && (
            <Collapse
              size="small"
              defaultActiveKey={hasUncertainSection ? ['sections'] : []}
              items={[
                {
                  key: 'sections',
                  label: (
                    <Space size={8}>
                      <Text strong>구간 처리 현황</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        총 {sections.length}개 구간
                      </Text>
                      {hasUncertainSection && (
                        <Tag color="orange" style={{ marginInlineEnd: 0 }}>
                          확인 필요 항목 있음
                        </Tag>
                      )}
                    </Space>
                  ),
                  children: (
                    <div
                      style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
                    >
                      {hasUncertainSection && (
                        <Alert
                          type="warning"
                          showIcon
                          message="일부 구간은 자동 추출되지 않았습니다. 해당 구간은 직접 확인하세요."
                        />
                      )}
                      {sectionGroups.map((group) => (
                        <div key={group.sheet}>
                          {group.items.map((section, i) => (
                            <div
                              key={`${section.sheet}|${section.label}|${i}`}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '2px 0',
                              }}
                            >
                              <Text style={{ fontSize: 13 }}>
                                <Text strong>{section.sheet}</Text>
                                {section.label !== section.sheet && (
                                  <Text type="secondary">
                                    {' '}
                                    — {section.label}
                                  </Text>
                                )}
                              </Text>
                              {renderSectionBadge(section)}
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          )}

          {/* 변경 목록: 표(sheet) 단위로 그룹핑하여 맥락이 드러나게 */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 20,
              maxHeight: 560,
              overflowY: 'auto',
            }}
          >
            {sheetGroups.map((group) => {
              const groupSelected = group.rows.filter((r) =>
                selectedKeys.includes(r.rowKey),
              ).length;
              return (
                <div key={group.sheet}>
                  {/* 시트(표) 소제목 */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginBottom: 6,
                      paddingBottom: 4,
                      borderBottom: '2px solid #f0f0f0',
                    }}
                  >
                    <FileExcelOutlined style={{ color: '#1677ff' }} />
                    <Text strong style={{ fontSize: 14 }}>
                      {group.sheet}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      변경 {group.rows.length}건
                      {groupSelected > 0 && ` · 선택 ${groupSelected}건`}
                    </Text>
                  </div>
                  <Table<RowData>
                    rowKey="rowKey"
                    rowSelection={rowSelection}
                    columns={columns}
                    dataSource={group.rows}
                    pagination={false}
                    size="small"
                    showHeader
                    loading={previewLoading}
                    rowClassName={(record) =>
                      record.match_count === 0 ? 'ant-table-row-disabled' : ''
                    }
                  />
                </div>
              );
            })}
          </div>

          {/* 적용 버튼 */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {selectedCount}건 선택됨
              </Text>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={applyLoading}
                disabled={selectedCount === 0}
                onClick={handleApply}
              >
                선택 항목 적용
              </Button>
            </Space>
          </div>
        </>
      )}

      {/* 파일 선택 후 미리보기 로딩 중 */}
      {previewLoading && rows.length === 0 && (
        <Alert
          type="info"
          showIcon
          message="대비표를 분석하는 중입니다..."
        />
      )}
    </div>
  );
}
