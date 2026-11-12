import { Group, Text } from '@mantine/core';
import type { Attachment } from '../../../api/types';
import { evidenceParts, isEvidenceRecognized, UNRECOGNIZED_TEXT } from '../../../lib/evidence';
import { formatCents } from '../../../lib/money';
import { hasTransportDetails, transportParts } from '../../../lib/travelDetails';
import { RegionBadge } from '../../RegionBadge';

const SUMMARY_MAX_WIDTH = 300;

function InvoiceLine({ attachment }: { attachment: Attachment }) {
  const invoice = attachment.invoice;
  if (!invoice) return null;
  const parts = [
    invoice.occurred_on ? `业务日期 ${invoice.occurred_on}` : '',
    invoice.issued_on ? `开票日期 ${invoice.issued_on}` : '开票日期未识别',
    invoice.seller_name || '销售方未识别',
    invoice.total_cents === null ? '金额未识别' : formatCents(invoice.total_cents),
    ...(hasTransportDetails(invoice.details) ? transportParts(invoice.details) : []),
  ];
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="xs" className="num" truncate maw={SUMMARY_MAX_WIDTH} title={parts.join(' · ')}>{parts.join(' · ')}</Text>
      <RegionBadge regionName={invoice.region_name} isNonlocal={invoice.is_nonlocal} showUnknown={false} />
    </Group>
  );
}

/** 识别信息：发票分开显示业务日期与开票日期；其他凭证显示实际发生日期。 */
export function RecognitionSummary({ attachment }: { attachment: Attachment }) {
  if (attachment.kind === 'invoice' && attachment.invoice) return <InvoiceLine attachment={attachment} />;
  if (!isEvidenceRecognized(attachment.evidence)) return <Text size="xs" c="dimmed">{UNRECOGNIZED_TEXT}</Text>;
  const text = evidenceParts(attachment.evidence, { orderNoTail: true }).join(' · ');
  return <Text size="xs" className="num" truncate maw={SUMMARY_MAX_WIDTH} title={text}>{text}</Text>;
}
