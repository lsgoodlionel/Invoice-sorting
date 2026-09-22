import { Alert, Text } from '@mantine/core';
import { IconKey } from '@tabler/icons-react';
import type { ImportAccountsInfo } from '../../../api/hooks/backup';

interface AccountsNoticeProps {
  accounts?: ImportAccountsInfo | null;
  /** 结果页用“已恢复”，预览用“将恢复” */
  isResult?: boolean;
}

/**
 * 包内登录账号的说明：单账套整套覆盖会恢复账号与密码，用醒目的橙色提示；
 * 合并模式与 SaaS 部署不导入账号，只作一句说明。包内没有账号时不显示。
 */
export function AccountsNotice({ accounts, isResult = false }: AccountsNoticeProps) {
  if (!accounts?.note) return null;
  if (!accounts.will_restore) {
    return <Text size="xs" c="dimmed">{accounts.note}</Text>;
  }
  const title = isResult ? '登录账号已恢复' : `将恢复 ${accounts.count} 个登录账号（含密码）`;
  return (
    <Alert color="orange" variant="light" icon={<IconKey size={16} />} title={title}>
      {accounts.note}
    </Alert>
  );
}
