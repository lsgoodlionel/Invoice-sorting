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

export function TripNotice({ expense }: { expense: ExpenseDetail }) {
  if (!expense.trip) return null;
  const trip = expense.trip;
  const documentTotal = trip.cost_lines.reduce((sum, line) => sum + line.amount_cents, 0);
  return (
    <Paper px="sm" py="sm" withBorder data-testid="trip-notice">
      <Text size="sm" fw={600}>{trip.destination}差旅 · {trip.start ?? '日期待补'} 至 {trip.end ?? '日期待补'}</Text>
      <Text size="xs" c="dimmed">去程 {trip.outbound_legs} 段 · 返程 {trip.return_legs} 段 · 住宿 {trip.lodging_nights} 晚{trip.expected_nights !== null ? ` / 预计 ${trip.expected_nights} 晚` : ''} · 当前总额 {formatCents(expense.amount_cents)}</Text>
      {trip.cost_lines.map((line) => <Group key={line.attachment_ids.join('-')} justify="space-between" gap="xs"><Text size="xs">{line.label}</Text><Text size="xs" className="num">{formatCents(line.amount_cents)}</Text></Group>)}
      {trip.cost_lines.length > 0 && <Group justify="space-between"><Text size="sm" fw={600}>费用合计</Text><Text size="sm" fw={600} className="num">{formatCents(documentTotal)}</Text></Group>}
      {trip.cost_lines.length > 0 && documentTotal !== expense.amount_cents && <Text size="xs" c="orange.8">清单总价与凭证费用合计不同，请核对手工修改的金额。</Text>}
      {trip.warnings.map((warning) => <Text key={warning} size="xs" c="orange.8">{warning}</Text>)}
    </Paper>
  );
}

interface AmountCompositionProps {
  amountCents: number;
  attachments: readonly Attachment[];
  costLines?: NonNullable<ExpenseDetail['trip']>['cost_lines'];
}

/** 金额构成：¥1,025.00 = 住宿 ¥720.00 + 交通 2 张 ¥305.00；与发票合计不一致时提示。 */
export function AmountComposition({ amountCents, attachments, costLines }: AmountCompositionProps) {
  if (costLines) return null;
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
