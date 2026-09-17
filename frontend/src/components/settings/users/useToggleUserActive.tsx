import { Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { errorMessage } from '../../../api/client';
import { useUpdateUser } from '../../../api/hooks/users';
import type { User } from '../../../api/types';

/** 启用直接生效；停用先二次确认。后端约束（400）原文提示。 */
export function useToggleUserActive() {
  const update = useUpdateUser();

  const setActive = (user: User, isActive: boolean) =>
    update.mutate(
      { id: user.id, patch: { is_active: isActive } },
      { onError: (error) => notifications.show({ color: 'red', title: '操作未完成', message: errorMessage(error) }) },
    );

  return (user: User) => {
    if (!user.is_active) {
      setActive(user, true);
      return;
    }
    modals.openConfirmModal({
      title: `停用用户「${user.display_name}」？`,
      children: <Text size="sm">该用户将立即退出登录，之后无法再登录；其历史操作记录保留并继续显示姓名。</Text>,
      labels: { confirm: '停用', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => setActive(user, false),
    });
  };
}
