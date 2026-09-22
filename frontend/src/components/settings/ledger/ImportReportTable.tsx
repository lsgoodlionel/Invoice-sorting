import { Badge, Button, List, Table, Text } from '@mantine/core';
import { Fragment, useState } from 'react';
import type { ImportDetailAction, ImportReportDetail, ImportReportItem, ImportReportKey } from '../../../api/hooks/backup';
import { reportLabel } from '../../../lib/ledgerTransfer';

const DETAIL_ACTIONS: Record<ImportDetailAction, { label: string; color: string }> = {
  added: { label: '新增', color: 'ink' },
  updated: { label: '更新', color: 'yellow' },
  skipped: { label: '跳过', color: 'gray' },
  conflict: { label: '冲突', color: 'orange' },
  failed: { label: '失败', color: 'red' },
  deleted: { label: '删除', color: 'red' },
};

interface ImportReportTableProps {
  items: readonly ImportReportItem[];
  /** 预览用“将…”，结果用“已…”并多一列失败 */
  variant: 'preview' | 'result';
}

const detailText = (detail: ImportReportDetail) => (detail.reason ? `${detail.label}：${detail.reason}` : detail.label);

function DetailList({ item }: { item: ImportReportItem }) {
  const truncated = item.truncated ?? 0;
  return (
    <List size="xs" spacing={2}>
      {(item.details ?? []).map((detail, index) => (
        <List.Item key={`${detail.action}-${index}`}>
          <Badge size="xs" variant="light" color={DETAIL_ACTIONS[detail.action]?.color ?? 'gray'} mr={6}>
            {DETAIL_ACTIONS[detail.action]?.label ?? detail.action}
          </Badge>
          {detailText(detail)}
        </List.Item>
      ))}
      {truncated > 0 && <List.Item><Text span size="xs" c="dimmed">{`另有 ${truncated} 条未列出`}</Text></List.Item>}
    </List>
  );
}

/** 新增/跳过/冲突按类别汇总，每类可展开明细。 */
export function ImportReportTable({ items, variant }: ImportReportTableProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<ImportReportKey>>(new Set());
  const isResult = variant === 'result';
  const columnCount = isResult ? 6 : 5;

  const toggle = (key: ImportReportKey) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <Table className="ledger-table" aria-label="导入明细">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>类别</Table.Th>
          <Table.Th ta="right">{isResult ? '已新增' : '将新增'}</Table.Th>
          <Table.Th ta="right">跳过（重复）</Table.Th>
          <Table.Th ta="right">冲突</Table.Th>
          {isResult && <Table.Th ta="right">失败</Table.Th>}
          <Table.Th />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((item) => {
          const label = reportLabel(item);
          const detailCount = item.details?.length ?? 0;
          return (
            <Fragment key={item.key}>
              <Table.Tr>
                <Table.Td>{label}</Table.Td>
                <Table.Td ta="right" className="num">{item.added}</Table.Td>
                <Table.Td ta="right" className="num">{item.skipped}</Table.Td>
                <Table.Td ta="right" className="num">
                  <Text span size="sm" c={item.conflicts > 0 ? 'orange' : undefined}>{item.conflicts}</Text>
                </Table.Td>
                {isResult && <Table.Td ta="right" className="num">{item.failed ?? 0}</Table.Td>}
                <Table.Td ta="right">
                  {detailCount > 0 && (
                    <Button size="compact-xs" variant="subtle" aria-label={`${label} 明细（${detailCount}）`} onClick={() => toggle(item.key)}>
                      {`${expanded.has(item.key) ? '收起' : '明细'}（${detailCount}）`}
                    </Button>
                  )}
                </Table.Td>
              </Table.Tr>
              {expanded.has(item.key) && (
                <Table.Tr>
                  <Table.Td colSpan={columnCount}><DetailList item={item} /></Table.Td>
                </Table.Tr>
              )}
            </Fragment>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
