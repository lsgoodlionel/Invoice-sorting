import { Alert, Button, CopyButton, Group, Stack, Text, TextInput } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconCopy, IconRefresh } from '@tabler/icons-react';
import { useMyReferrals, useResetReferral } from '../../../api/hooks/referrals';
import type { MyReferrals } from '../../../api/signupTypes';
import { referralLink } from '../../../lib/signup';
import { FormError } from '../users/FormError';
import { ReferralInviteeList } from './ReferralInviteeList';

const INTRO_APPROVAL = '把链接发给朋友：对方填写申请后，平台审核通过即可注册，并获得自己的独立账本。';
const INTRO_DIRECT = '把链接发给朋友：对方填写资料后会直接收到注册链接，并获得自己的独立账本。';
const DISABLED_HINT = '你的推荐资格已被平台停用，推荐链接暂时无法使用。如有疑问，请联系平台管理员。';

function useConfirmReset() {
  const reset = useResetReferral();
  const confirm = () =>
    modals.openConfirmModal({
      title: '重置推荐链接？',
      children: <Text size="sm">旧链接会立即失效，已经发出去的旧链接将无法再用于申请。已完成的推荐记录不受影响。</Text>,
      labels: { confirm: '重置', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        reset.mutate(undefined, { onSuccess: () => notifications.show({ color: 'ink', message: '已生成新的推荐链接' }) }),
    });
  return { confirm, reset };
}

function ReferralLinkRow({ link }: { link: string }) {
  return (
    <Group gap="xs" wrap="nowrap" align="flex-end">
      <TextInput label="我的推荐链接" value={link} readOnly className="num" style={{ flex: 1 }} />
      <CopyButton value={link}>
        {({ copied, copy }) => (
          <Button variant="outline" leftSection={<IconCopy size={14} stroke={1.6} />} onClick={copy}>
            {copied ? '已复制' : '复制链接'}
          </Button>
        )}
      </CopyButton>
    </Group>
  );
}

function introOf(data: MyReferrals): string {
  if (data.require_approval) return INTRO_APPROVAL;
  const quota = `本月直接注册名额 ${data.used_this_month}/${data.monthly_quota}，用完后转为平台审核。`;
  return `${INTRO_DIRECT}${quota}`;
}

/** 设置 → 推荐好友：推荐链接（复制、重置）与推荐记录。 */
export function ReferralSection() {
  const { data, error, isLoading } = useMyReferrals(true);
  const { confirm, reset } = useConfirmReset();
  if (isLoading) return null;
  if (!data) return <FormError error={error} />;
  const link = data.is_disabled ? null : referralLink(data, window.location.origin);

  return (
    <Stack gap="sm">
      {link ? (
        <>
          <Text size="xs" c="dimmed">{introOf(data)}</Text>
          <ReferralLinkRow link={link} />
          <Group>
            <Button size="xs" variant="subtle" color="red" loading={reset.isPending}
              leftSection={<IconRefresh size={14} stroke={1.6} />} onClick={confirm}>
              重置链接
            </Button>
          </Group>
          <FormError error={reset.error} />
        </>
      ) : (
        <Alert color="orange" variant="light" data-testid="referral-disabled">{DISABLED_HINT}</Alert>
      )}
      <ReferralInviteeList items={data.referrals} />
    </Stack>
  );
}
