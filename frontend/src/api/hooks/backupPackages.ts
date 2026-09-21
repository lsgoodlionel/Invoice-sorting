import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { queryKeys } from './keys';

/** 服务器上保留的一份备份文件（账套完整备份或平台数据库备份共用此形状）。 */
export interface BackupFile {
  name: string;
  size: number;
  created_at: string;
}

const PACKAGES_PATH = '/backup/packages';

export const backupPackagesApi = {
  /** 最新在前，服务器保留最近 10 份 */
  list: () => api.get<BackupFile[]>(PACKAGES_PATH),
};

/** 下载地址（浏览器直接下载，走同源会话 Cookie）。 */
export const backupPackageUrl = (name: string) => `/api${PACKAGES_PATH}/${encodeURIComponent(name)}`;

export const useBackupPackages = () =>
  useQuery({ queryKey: queryKeys.backupPackages, queryFn: backupPackagesApi.list });
