import { Pagination, Stack, Text, TextInput } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '../../../api/client';
import { usePlatformReferrals, useSetReferrerDisabled } from '../../../api/hooks/platformSignup';
import type { AccountRef, PlatformReferral } from '../../../api/signupTypes';
import { ReferralTable } from './ReferralTable';

const PAGE_SIZE = 20;

function useToggleReferrer() {
  const update = useSetReferrerDisabled();
  const apply = (account: AccountRef, isDisabled: boolean) =>
    update.mutate(
      { accountId: account.account_id, isDisabled },
      {
        onSuccess: () => notifications.show({ color: 'ink', message: `已${isDisabled ? '停用' : '恢复'} ${account.display_name} 的推荐资格` }),
        onError: (error) => notifications.show({ color: 'red', title: '操作未完成', message: errorMessage(error) }),
      },
    );
  return ({ referrer, is_referrer_disabled: isDisabled }: PlatformReferral) => {
    if (!referrer) return;
    if (isDisabled) {
      apply(referrer, false);
      return;
    }
    modals.openConfirmModal({
      title: `停用 ${referrer.display_name} 的推荐资格？`,
      children: <Text size="sm">其推荐链接立即失效，也不能再重置出新链接；已完成的推荐记录保留。</Text>,
      labels: { confirm: '停用', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => apply(referrer, true),
    });
  };
}

/** 推荐记录：谁推荐了谁、结果如何；可停用某人的推荐资格。 */
export function ReferralRecords() {
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const { data, isLoading } = usePlatformReferrals({ q: keyword.trim(), page });
  const toggle = useToggleReferrer();
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / (data?.page_size ?? PAGE_SIZE)));

  return (
    <Stack gap="sm">
      <TextInput size="xs" w={240} placeholder="搜索推荐人或被推荐人邮箱" leftSection={<IconSearch size={14} stroke={1.6} />}
        value={keyword} onChange={(event) => { setKeyword(event.currentTarget.value); setPage(1); }} />
      {!isLoading && data && total > 0 && <ReferralTable referrals={data.items} onToggle={toggle} />}
      {!isLoading && total === 0 && <Text size="sm" c="dimmed">还没有推荐记录。</Text>}
      {pages > 1 && <Pagination size="sm" value={page} total={pages} onChange={setPage} />}
    </Stack>
  );
}
