import { Anchor, Table, Text } from '@mantine/core';
import { Link } from 'react-router';
import type { DateBasis, ExpenseStatus, StatsGroupBy, StatsRow } from '../../api/types';
import { formatCents } from '../../lib/money';
import { ALL_STATUSES, STATUS_META } from '../../lib/status';
import { statsCellLink } from '../../lib/statsDrill';

interface StatsCrossTableProps {
  rows: readonly StatsRow[];
  start: string;
  end: string;
  dateBasis: DateBasis;
  groupBy: StatsGroupBy;
}

export function StatsCrossTable({ rows, start, end, dateBasis, groupBy }: StatsCrossTableProps) {
  if (rows.length === 0) return <Text size="sm" c="dimmed">本期没有数据。</Text>;
  const link = (row: StatsRow, status: ExpenseStatus | null) => statsCellLink({ start, end, dateBasis, groupBy, row, status });
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={820}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>分组</Table.Th>
            {ALL_STATUSES.map((status) => (
              <Table.Th key={status} ta="right"><span className="status-dot" data-status={status} />{STATUS_META[status].shortLabel}</Table.Th>
            ))}
            <Table.Th ta="right">合计</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.key}>
              <Table.Td><Text size="sm" truncate maw={200}>{row.label}</Text></Table.Td>
              {ALL_STATUSES.map((status) => {
                const cell = row.by_status[status];
                return (
                  <Table.Td key={status} ta="right" className="num">
                    {cell && cell.count > 0 ? (
                      <Anchor component={Link} to={link(row, status)} size="sm" c="inherit" className="cell-link" title={`${cell.count} 条`}>
                        {formatCents(cell.amount_cents, { symbol: false })}
                      </Anchor>
                    ) : (
                      <Text span size="sm" c="paper.4">—</Text>
                    )}
                  </Table.Td>
                );
              })}
              <Table.Td ta="right" className="num" fw={600}>
                <Anchor component={Link} to={link(row, null)} size="sm" c="inherit" className="cell-link">{formatCents(row.total_cents)}</Anchor>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
