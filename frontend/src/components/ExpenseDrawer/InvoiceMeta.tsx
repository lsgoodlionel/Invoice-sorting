import { Group, Text } from '@mantine/core';
import type { ExpenseDetail } from '../../api/types';
import { collectOrderNos, describeRegion } from '../../lib/region';

/** 基本信息区的只读发票信息：三日期、开票地区与订单号。 */
export function InvoiceMeta({ expense }: { expense: Pick<ExpenseDetail, 'spent_on' | 'issued_on' | 'created_on' | 'region_name' | 'is_nonlocal' | 'attachments'> }) {
  const orderNos = collectOrderNos(expense.attachments);
  return (
    <Group gap="lg" wrap="wrap" data-testid="invoice-meta">
      <Text size="sm"><Text span c="dimmed" size="sm">业务发生日期：</Text><span className="num">{expense.spent_on}</span></Text>
      <Text size="sm"><Text span c="dimmed" size="sm">发票开票日期：</Text><span className="num">{expense.issued_on ?? '—'}</span></Text>
      <Text size="sm"><Text span c="dimmed" size="sm">凭证填报日期：</Text><span className="num">{expense.created_on ?? '—'}</span></Text>
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
