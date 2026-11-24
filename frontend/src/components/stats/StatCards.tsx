import { Anchor, SimpleGrid, Stack, Text } from '@mantine/core';
import { Link } from 'react-router';
import type { DateBasis, ExpenseStatus, StatsTotals } from '../../api/types';
import { expensesLink } from '../../lib/expenseFilters';
import { formatCents } from '../../lib/money';

interface CardProps {
  label: string;
  cents: number;
  hint: string;
  isLead?: boolean;
  to: string;
}

function StatCard({ label, cents, hint, to, isLead = false }: CardProps) {
  return (
    <Stack gap={2} className="stat-card" data-lead={isLead || undefined}>
      <Text className="section-label">{label}</Text>
      <Anchor component={Link} to={to} c="inherit" className="cell-link num" fw={700} fz={isLead ? 30 : 24}>{formatCents(cents)}</Anchor>
      <Text size="xs" c="dimmed">{hint}</Text>
    </Stack>
  );
}

export function StatCards({ totals, start, end, dateBasis }: { totals: StatsTotals; start: string; end: string; dateBasis: DateBasis }) {
  const link = (statuses: ExpenseStatus[]) => expensesLink({ period: { preset: 'custom', start, end }, dateBasis, statuses });
  return (
    <Stack gap={4}>
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing={0} className="stat-grid">
        <StatCard label="本期支出" cents={totals.spent_cents} hint="不含作废" isLead to={link(['spent', 'invoiced', 'complete', 'sent', 'reimbursed'])} />
        <StatCard label="待处理" cents={totals.pending_cents} hint="已支出 / 已开票 / 凭证齐全" to={link(['spent', 'invoiced', 'complete'])} />
        <StatCard label="在途" cents={totals.in_transit_cents} hint="已外发未到账" to={link(['sent'])} />
        <StatCard label="已报销" cents={totals.reimbursed_cents} hint="实际到账金额" to={link(['reimbursed'])} />
      </SimpleGrid>
      <Text size="xs" c="dimmed" className="num">不报销 / 作废（单列）：{formatCents(totals.void_cents)}</Text>
    </Stack>
  );
}
