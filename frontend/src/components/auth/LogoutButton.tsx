import { Button, Text, type ButtonProps } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconLogout } from '@tabler/icons-react';
import { useLogout } from '../../api/hooks/auth';

/** 确认后退出登录；成功后 AuthGate 切回登录页。 */
export function LogoutButton(props: Omit<ButtonProps, 'onClick' | 'loading'>) {
  const logout = useLogout();

  const confirm = () =>
    modals.openConfirmModal({
      title: '退出登录？',
      children: <Text size="sm">退出后需要重新输入密码才能继续使用。</Text>,
      labels: { confirm: '退出', cancel: '取消' },
      confirmProps: { variant: 'filled' },
      onConfirm: () => logout.mutate(),
    });

  return (
    <Button leftSection={<IconLogout size={16} stroke={1.6} />} {...props} loading={logout.isPending} onClick={confirm}>
      退出登录
    </Button>
  );
}
