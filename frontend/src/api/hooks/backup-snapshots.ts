import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { queryKeys } from './keys';

/** 服务器上的数据库快照：手动创建（manual）或升级前自动备份（upgrade）。 */
export interface DatabaseSnapshot {
  name: string;
  kind: 'manual' | 'upgrade';
  size: number;
  created_at: string;
}

const SNAPSHOTS_PATH = '/backup/snapshots';

export const snapshotsApi = {
  list: () => api.get<DatabaseSnapshot[]>(SNAPSHOTS_PATH),
  create: () => api.post<{ file: string; name: string }>('/backup'),
};

/** 快照下载地址（浏览器直接下载，走同源会话 Cookie）。 */
export const snapshotDownloadUrl = (name: string) => `/api${SNAPSHOTS_PATH}/${encodeURIComponent(name)}`;

export const useDatabaseSnapshots = () =>
  useQuery({ queryKey: queryKeys.backupSnapshots, queryFn: snapshotsApi.list });

export function useCreateSnapshot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: snapshotsApi.create,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.backupSnapshots }),
  });
}
