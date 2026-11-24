import { Anchor, Table, Text } from '@mantine/core';
import { Link } from 'react-router';
import type { DateBasis, StatsColumn, StatsCrossBy, StatsGroupBy, StatsRow } from '../../api/types';
import { formatCents } from '../../lib/money';
import { statsCellLink } from '../../lib/statsDrill';

interface StatsCrossTableProps {
  rows: readonly StatsRow[];
  start: string;
  end: string;
  dateBasis: DateBasis;
  groupBy: StatsGroupBy;
  crossBy: StatsCrossBy;
  columns: readonly StatsColumn[];
}

export function StatsCrossTable({ rows, start, end, dateBasis, groupBy, crossBy, columns }: StatsCrossTableProps) {
  if (rows.length === 0) return <Text size="sm" c="dimmed">本期没有数据。</Text>;
  const link = (row: StatsRow, column: StatsColumn | null) => statsCellLink({ start, end, dateBasis, groupBy, row, status: null, crossBy, column });
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={820}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>分组</Table.Th>
            {columns.map((column) => (
              <Table.Th key={column.key} ta="right">{column.label}</Table.Th>
            ))}
            <Table.Th ta="right">合计</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.key}>
              <Table.Td><Anchor component={Link} to={link(row, null)} size="sm" c="inherit" className="cell-link">{row.label}</Anchor></Table.Td>
              {columns.map((column) => {
                const cell = row.cells?.[column.key] ?? row.by_status[column.key as keyof typeof row.by_status];
                return (
                  <Table.Td key={column.key} ta="right" className="num">
                    {cell && cell.count > 0 ? (
                      <Anchor component={Link} to={link(row, column)} size="sm" c="inherit" className="cell-link" title={`${cell.count} 条`}>
                        {formatCents(cell.amount_cents, { symbol: false })}
                      </Anchor>
                    ) : (
                      <Text span size="sm" c="paper.4">—</Text>
                    )}
                  </Table.Td>
                );
              })}
              <Table.Td ta="right" className="num" fw={600}>
                <Anchor component={Link} to={link(row, null)} size="sm" c="inherit" className="cell-link" title={`${row.total_count ?? ''} 条`}>{formatCents(row.total_cents)}</Anchor>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
