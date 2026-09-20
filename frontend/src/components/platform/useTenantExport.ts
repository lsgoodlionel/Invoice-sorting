import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { platformMembersApi } from '../../api/hooks/platformMembers';
import type { ExportJob } from '../../api/types';

const POLL_MS = 1500;

export interface TenantExport {
  start: () => void;
  isRunning: boolean;
  job: ExportJob | null;
  error: unknown;
}

/**
 * 导出账套：POST 登记任务后轮询状态，done 时给出下载地址、failed 时给出后端原因。
 * 轮询只在任务进行中进行，完成后自动停止。
 */
export function useTenantExport(slug: string): TenantExport {
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () => platformMembersApi.startExport(slug),
    onSuccess: (created) => setJobId(created.job),
    meta: { silent: true },
  });
  const status = useQuery({
    queryKey: ['platform', 'export', slug, jobId],
    queryFn: () => platformMembersApi.exportStatus(slug, jobId ?? ''),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? POLL_MS : false),
    retry: false,
    meta: { silent: true },
  });
  const job = status.data ?? start.data ?? null;
  return {
    start: () => {
      setJobId(null);
      start.mutate();
    },
    isRunning: start.isPending || job?.status === 'running',
    job,
    error: start.error ?? status.error,
  };
}
