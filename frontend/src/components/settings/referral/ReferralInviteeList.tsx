import { Badge, Group, Stack, Text } from '@mantine/core';
import type { ApplicationStatus, MyReferralItem } from '../../../api/signupTypes';
import { APPLICATION_STATUS_COLORS, REFERRAL_STATUS_LABELS, maskEmail } from '../../../lib/signup';

const SUMMARY_ORDER: readonly ApplicationStatus[] = ['registered', 'approved', 'pending', 'rejected'];

function summaryOf(items: readonly MyReferralItem[]): string {
  return SUMMARY_ORDER.map((status) => [status, items.filter((item) => item.status === status).length] as const)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${REFERRAL_STATUS_LABELS[status]} ${count}`)
    .join(' · ');
}

/** 已推荐人数与各自状态；只显示对方邮箱的脱敏形式（后端已脱敏，这里再兜底一次）。 */
export function ReferralInviteeList({ items }: { items: readonly MyReferralItem[] }) {
  if (items.length === 0) return <Text size="sm" c="dimmed">还没有人通过你的链接申请。</Text>;
  return (
    <Stack gap={6}>
      <Text size="sm" data-testid="referral-summary">
        已推荐 <Text span fw={600} className="num">{items.length}</Text> 人（{summaryOf(items)}）
      </Text>
      {items.map((item) => (
        <Group key={item.id} gap="sm" wrap="nowrap" data-testid="referral-invitee">
          <Text size="sm" className="num" miw={180}>{maskEmail(item.email_masked)}</Text>
          <Badge size="sm" variant="light" color={APPLICATION_STATUS_COLORS[item.status]}>
            {REFERRAL_STATUS_LABELS[item.status]}
          </Badge>
          <Text size="xs" c="dimmed" className="num">{item.created_at.slice(0, 10)}</Text>
        </Group>
      ))}
    </Stack>
  );
}
