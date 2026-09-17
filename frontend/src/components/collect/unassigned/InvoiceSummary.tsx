import { Group, Text } from '@mantine/core';
import type { Attachment } from '../../../api/types';
import { formatCents } from '../../../lib/money';
import { RegionBadge } from '../../RegionBadge';

/** 识别信息：开票日期 · 销售方 · 金额 · 地区；非发票显示“—”。 */
export function InvoiceSummary({ attachment }: { attachment: Attachment }) {
  const invoice = attachment.invoice;
  if (attachment.kind !== 'invoice' || !invoice) return <Text size="xs" c="dimmed">—</Text>;
  const parts = [
    invoice.issued_on ?? '日期未识别',
    invoice.seller_name || '销售方未识别',
    invoice.total_cents === null ? '金额未识别' : formatCents(invoice.total_cents),
  ];
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="xs" className="num" truncate maw={300} title={parts.join(' · ')}>{parts.join(' · ')}</Text>
      <RegionBadge regionName={invoice.region_name} isNonlocal={invoice.is_nonlocal} showUnknown={false} />
    </Group>
  );
}
