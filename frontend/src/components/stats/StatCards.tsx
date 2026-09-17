import { SimpleGrid, Stack, Text } from '@mantine/core';
import type { StatsTotals } from '../../api/types';
import { formatCents } from '../../lib/money';

interface CardProps {
  label: string;
  cents: number;
  hint: string;
  isLead?: boolean;
}

function StatCard({ label, cents, hint, isLead = false }: CardProps) {
  return (
    <Stack gap={2} className="stat-card" data-lead={isLead || undefined}>
      <Text className="section-label">{label}</Text>
      <Text className="num" fw={700} fz={isLead ? 30 : 24}>{formatCents(cents)}</Text>
      <Text size="xs" c="dimmed">{hint}</Text>
    </Stack>
  );
}

export function StatCards({ totals }: { totals: StatsTotals }) {
  return (
    <Stack gap={4}>
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing={0} className="stat-grid">
        <StatCard label="本期支出" cents={totals.spent_cents} hint="不含作废" isLead />
        <StatCard label="待处理" cents={totals.pending_cents} hint="已支出 / 已开票 / 凭证齐全" />
        <StatCard label="在途" cents={totals.in_transit_cents} hint="已外发未到账" />
        <StatCard label="已报销" cents={totals.reimbursed_cents} hint="实际到账金额" />
      </SimpleGrid>
      <Text size="xs" c="dimmed" className="num">不报销 / 作废（单列）：{formatCents(totals.void_cents)}</Text>
    </Stack>
  );
}
