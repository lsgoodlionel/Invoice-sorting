import { Badge, Button, Table, Text } from '@mantine/core';
import type { PlatformReferral } from '../../../api/signupTypes';
import { APPLICATION_STATUS_COLORS, APPLICATION_STATUS_LABELS, formatDateTime } from '../../../lib/signup';

const TABLE_MIN_WIDTH = 860;

interface ReferralTableProps {
  referrals: readonly PlatformReferral[];
  onToggle: (referral: PlatformReferral) => void;
}

function ReferrerCell({ referral }: { referral: PlatformReferral }) {
  if (!referral.referrer) return <Text size="sm" c="dimmed">账号已删除</Text>;
  return (
    <>
      <Text size="sm">{referral.referrer.display_name}</Text>
      <Text size="xs" c="dimmed" className="num">{referral.referrer.username}</Text>
      {referral.is_referrer_disabled && <Badge size="xs" variant="light" color="red">推荐资格已停用</Badge>}
    </>
  );
}

function ReferralRow({ referral, onToggle }: { referral: PlatformReferral; onToggle: ReferralTableProps['onToggle'] }) {
  const action = referral.is_referrer_disabled ? '恢复推荐资格' : '停用推荐资格';
  return (
    <Table.Tr data-testid={`referral-row-${referral.application_id}`}>
      <Table.Td><ReferrerCell referral={referral} /></Table.Td>
      <Table.Td><Text size="sm" className="num">{referral.referee_email}</Text></Table.Td>
      <Table.Td><Text size="sm">{referral.tenant ? `${referral.tenant.name}（${referral.tenant.slug}）` : '—'}</Text></Table.Td>
      <Table.Td><Text size="xs" c="dimmed" className="num">{formatDateTime(referral.created_at)}</Text></Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={APPLICATION_STATUS_COLORS[referral.status]}>
          {APPLICATION_STATUS_LABELS[referral.status]}
        </Badge>
        {referral.is_auto_approved && <Text size="xs" c="dimmed">直接注册</Text>}
      </Table.Td>
      <Table.Td>
        {referral.referrer && (
          <Button size="compact-xs" variant="subtle" color={referral.is_referrer_disabled ? 'ink' : 'red'}
            aria-label={`${action}：${referral.referrer.username}`} onClick={() => onToggle(referral)}>
            {action}
          </Button>
        )}
      </Table.Td>
    </Table.Tr>
  );
}

export function ReferralTable({ referrals, onToggle }: ReferralTableProps) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>推荐人</Table.Th>
            <Table.Th>被推荐人邮箱</Table.Th>
            <Table.Th>账套</Table.Th>
            <Table.Th>时间</Table.Th>
            <Table.Th>结果</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {referrals.map((referral) => (
            <ReferralRow key={referral.application_id} referral={referral} onToggle={onToggle} />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
