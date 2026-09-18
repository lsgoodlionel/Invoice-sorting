import { Group, Paper, Text } from '@mantine/core';
import { IconBed } from '@tabler/icons-react';
import type { Attachment } from '../../api/types';
import { formatCents } from '../../lib/money';
import { lodgingInfoText } from '../../lib/travelDetails';
import { amountComposition } from '../../lib/travelInvoice';

/** 住宿记录顶部的住宿信息条（取自酒店订单）。 */
export function LodgingBanner({ attachments }: { attachments: readonly Attachment[] }) {
  const text = lodgingInfoText(attachments);
  if (!text) return null;
  return (
    <Paper className="lodging-banner" px="sm" py={6} radius={0} data-testid="lodging-banner">
      <Group gap={6} wrap="nowrap">
        <IconBed size={16} stroke={1.6} aria-hidden />
        <Text size="sm" className="num">{text}</Text>
      </Group>
    </Paper>
  );
}

interface AmountCompositionProps {
  amountCents: number;
  attachments: readonly Attachment[];
}

/** 金额构成：¥1,025.00 = 住宿 ¥720.00 + 交通 2 张 ¥305.00；与发票合计不一致时提示。 */
export function AmountComposition({ amountCents, attachments }: AmountCompositionProps) {
  const info = amountComposition(amountCents, attachments);
  if (!info) return null;
  return (
    <Group gap={6} justify="flex-end" wrap="wrap" data-testid="amount-composition">
      <Text size="xs" c="dimmed" className="num">{info.text}</Text>
      {info.isMismatch && (
        <Text size="xs" c="orange.8" fw={600} className="num">与发票合计 {formatCents(info.invoiceTotalCents)} 不一致</Text>
      )}
    </Group>
  );
}
