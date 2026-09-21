import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { MailCheckResult, MailSettings, MailSettingsPatch } from '../mailTypes';
import { queryKeys } from './keys';

// 平台管理员：邮件（SMTP）设置、测试连接与测试邮件。测试都用「已保存并生效」的配置。

const BASE = '/platform/mail-settings';

export const platformMailApi = {
  settings: () => api.get<MailSettings>(BASE),
  patch: (patch: MailSettingsPatch) => api.patch<MailSettings>(BASE, patch),
  testConnection: () => api.post<MailCheckResult>(`${BASE}/test-connection`),
  testEmail: (to: string) => api.post<MailCheckResult>(`${BASE}/test-email`, { to }),
};

export const useMailSettings = () =>
  useQuery({ queryKey: queryKeys.platformMailSettings, queryFn: platformMailApi.settings });

/** 「是否已配置邮件」提示用：静默查询，失败时不弹通知。 */
export const useMailConfigured = (): boolean | undefined => {
  const { data } = useQuery({
    queryKey: queryKeys.platformMailSettings,
    queryFn: platformMailApi.settings,
    meta: { silent: true },
  });
  return data?.is_configured;
};

function useRefreshAfterSave() {
  const client = useQueryClient();
  return (next: MailSettings) => {
    client.setQueryData(queryKeys.platformMailSettings, next);
    // 注册设置里的「是否已配置邮件」随之变化
    return client.invalidateQueries({ queryKey: queryKeys.platformSignupSettings });
  };
}

export function usePatchMailSettings() {
  const refresh = useRefreshAfterSave();
  return useMutation({ mutationFn: platformMailApi.patch, onSuccess: refresh, meta: { silent: true } });
}

/** 测试结果写入「最近一次验证」，完成后重新读取设置。 */
function useMailCheck<T>(run: (input: T) => Promise<MailCheckResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSettled: () => client.invalidateQueries({ queryKey: queryKeys.platformMailSettings }),
    meta: { silent: true },
  });
}

export const useTestMailConnection = () => useMailCheck<void>(() => platformMailApi.testConnection());
export const useSendTestMail = () => useMailCheck<string>(platformMailApi.testEmail);
