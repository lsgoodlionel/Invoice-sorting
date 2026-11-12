import { Group, Paper, Text } from '@mantine/core';
import { IconBed } from '@tabler/icons-react';
import type { Attachment, ExpenseDetail } from '../../api/types';
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

/** 住宿发票可先建账；缺少实际入住/离店日期时明确提示补单。 */
export function TravelDateNotice({ expense }: { expense: ExpenseDetail }) {
  if (!expense.travel_dates_missing) return null;
  return (
    <Paper px="sm" py={8} withBorder style={{ borderColor: 'var(--mantine-color-orange-4)' }}>
      <Text size="sm" c="orange.8" fw={600}>住宿时间待完善</Text>
      <Text size="xs" c="dimmed">请补充酒店订单或支付水单；开票日期不会用于往返交通自动关联。</Text>
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
        <Text size="xs" c="orange.8" fw={600} className="num">与凭证净额 {formatCents(info.documentTotalCents)} 不一致</Text>
      )}
    </Group>
  );
}
