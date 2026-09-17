import { Group, Text } from '@mantine/core';
import type { ExpenseDetail } from '../../api/types';
import { collectOrderNos, describeRegion } from '../../lib/region';

/** 基本信息区的只读发票信息：开票地区与订单号。 */
export function InvoiceMeta({ expense }: { expense: Pick<ExpenseDetail, 'region_name' | 'is_nonlocal' | 'attachments'> }) {
  const orderNos = collectOrderNos(expense.attachments);
  if (!expense.region_name && orderNos.length === 0) return null;
  return (
    <Group gap="lg" data-testid="invoice-meta">
      <Text size="sm">
        <Text span c="dimmed" size="sm">开票地区：</Text>
        <Text span size="sm" c={expense.is_nonlocal ? 'orange.8' : undefined} fw={expense.is_nonlocal ? 600 : undefined}>
          {describeRegion(expense.region_name, expense.is_nonlocal)}
        </Text>
      </Text>
      <Text size="sm">
        <Text span c="dimmed" size="sm">订单号：</Text>
        <span className="num">{orderNos.length ? orderNos.join('、') : '—'}</span>
      </Text>
    </Group>
  );
}
