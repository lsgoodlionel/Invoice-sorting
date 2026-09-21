import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { BackupFile } from './backupPackages';
import { queryKeys } from './keys';

// 平台管理员：平台数据库（账号、账套、套餐、授权、邮件设置）的备份，与各账套的备份无关。

const BASE = '/platform/backups';

/** 新建备份的返回：备份信息，可能附带服务端提示。 */
export interface PlatformBackupCreated extends BackupFile {
  notice?: string;
}

/** 列表接口：备份文件与固定的安全提示。 */
export interface PlatformBackupList {
  items: BackupFile[];
  notice?: string;
}

export const platformBackupsApi = {
  list: () => api.get<PlatformBackupList>(BASE),
  create: () => api.post<PlatformBackupCreated>(BASE),
};

export const platformBackupUrl = (name: string) => `/api${BASE}/${encodeURIComponent(name)}`;

export const usePlatformBackups = () =>
  useQuery({ queryKey: queryKeys.platformBackups, queryFn: platformBackupsApi.list });

/** 错误由界面就地显示，不弹全局提示。 */
export function useCreatePlatformBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: platformBackupsApi.create,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.platformBackups }),
    meta: { silent: true },
  });
}
