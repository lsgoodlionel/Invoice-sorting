import { Group, Text } from '@mantine/core';
import type { Attachment } from '../../../api/types';
import { evidenceParts, isEvidenceRecognized, UNRECOGNIZED_TEXT } from '../../../lib/evidence';
import { formatCents } from '../../../lib/money';
import { RegionBadge } from '../../RegionBadge';

const SUMMARY_MAX_WIDTH = 300;

function InvoiceLine({ attachment }: { attachment: Attachment }) {
  const invoice = attachment.invoice;
  if (!invoice) return null;
  const parts = [
    invoice.issued_on ?? '日期未识别',
    invoice.seller_name || '销售方未识别',
    invoice.total_cents === null ? '金额未识别' : formatCents(invoice.total_cents),
  ];
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="xs" className="num" truncate maw={SUMMARY_MAX_WIDTH} title={parts.join(' · ')}>{parts.join(' · ')}</Text>
      <RegionBadge regionName={invoice.region_name} isNonlocal={invoice.is_nonlocal} showUnknown={false} />
    </Group>
  );
}

/** 识别信息：发票显示开票日期 · 销售方 · 金额 · 地区；其他凭证显示类型 · 日期 · 金额 · 商户 · 订单号尾号。 */
export function RecognitionSummary({ attachment }: { attachment: Attachment }) {
  if (attachment.kind === 'invoice' && attachment.invoice) return <InvoiceLine attachment={attachment} />;
  if (!isEvidenceRecognized(attachment.evidence)) return <Text size="xs" c="dimmed">{UNRECOGNIZED_TEXT}</Text>;
  const text = evidenceParts(attachment.evidence, { orderNoTail: true }).join(' · ');
  return <Text size="xs" className="num" truncate maw={SUMMARY_MAX_WIDTH} title={text}>{text}</Text>;
}
