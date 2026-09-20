import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { queryKeys } from './keys';

/** 一次打包与上传的结果（后端 diagnostics 模块）。 */
export interface DiagnosticsReport {
  created_at: string;
  reason: 'manual' | 'crash' | 'error';
  fingerprint: string;
  package: string;
  size: number;
  residue: string[];
  is_truncated: boolean;
  is_uploaded: boolean;
  repo_path: string;
  message: string;
}

export interface DiagnosticsStatus {
  upload_enabled: boolean;
  repo: string;
  app: string;
  instance: string;
  log_file: string;
  last: DiagnosticsReport | null;
  throttle: { daily_used: number; daily_remaining: number; tracked_fingerprints: number };
}

export interface CollectOptions {
  upload: boolean;
}

export const diagnosticsApi = {
  status: () => api.get<DiagnosticsStatus>('/diagnostics/status'),
  collect: (options: CollectOptions) =>
    api.post<DiagnosticsReport>('/diagnostics/collect', { upload: options.upload, reason: 'manual' }),
};

/** 诊断状态（仅管理员）。失败时静默：这只是设置页的一块信息，不该弹全局错误。 */
export const useDiagnosticsStatus = (enabled = true) =>
  useQuery({
    queryKey: queryKeys.diagnosticsStatus,
    queryFn: diagnosticsApi.status,
    enabled,
    retry: false,
    meta: { silent: true },
  });

/** 生成诊断包按需触发，所以用 mutation；成功后刷新状态里的“最近一次”。 */
export function useCollectDiagnostics() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (options: CollectOptions) => diagnosticsApi.collect(options),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.diagnosticsStatus }),
  });
}
