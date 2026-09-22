// 备份与搬迁（设置 → 备份与搬迁）的备份任务与导入接口；服务器保留的备份列表见 backupPackages.ts。
// 字段形状以 docs/账本搬迁_设计.md 与本文件为准，对齐时只需改这里。
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api, request } from '../client';
import { queryKeys } from './keys';

export type BackupJobStatus = 'running' | 'done' | 'failed';
/** 导入会话状态：uploading → ready（已出预览）→ running → done/failed */
export type ImportSessionStatus = 'uploading' | 'ready' | BackupJobStatus;

/** 导出任务：POST 登记、GET 轮询；done 时 download_url 可下载。 */
export interface LedgerExportJob {
  job: string;
  status: BackupJobStatus;
  download_url: string;
  file?: string;
  size?: number;
  error?: string;
}

export interface ImportUploadInput {
  filename: string;
  size: number;
  part_size: number;
  sha256: string;
}

/** 登记上传：后端可调整片大小，前端以返回的 part_size 为准。 */
export interface ImportUpload {
  upload_id: string;
  part_size: number;
}

export type ImportMode = 'merge' | 'replace';

/**
 * 报告按对象类别汇总。后端现有类别：records 记录、attachments 附件、users 用户、categories 分类、
 * projects 经费项目、rules 凭证规则、memories 分类记忆、batches 批次、exports 资料包生成记录、
 * settings 系统设置（明细 label 为设置项中文名，reason 形如「原值 → 新值」）、
 * accounts 登录账号（仅单账套覆盖模式：每个账号是新建、更新密码还是保留）。
 */
export type ImportReportKey = string;

export type ImportDetailAction = 'added' | 'updated' | 'skipped' | 'conflict' | 'failed' | 'deleted';

export interface ImportReportDetail {
  action: ImportDetailAction;
  /** 对象的可读名称，如“发票 04403”“分类 图书” */
  label: string;
  reason?: string;
}

export interface ImportReportItem {
  key: ImportReportKey;
  /** 后端给出的中文类别名；缺省时前端按 key 兜底 */
  label?: string;
  added: number;
  /** 以导入包为准改写的数量（设置、账号更新密码等） */
  updated?: number;
  /** 仅覆盖恢复账号：本地多出而被删除的账号数 */
  deleted?: number;
  skipped: number;
  conflicts: number;
  failed?: number;
  /** 明细（后端有条数上限） */
  details?: ImportReportDetail[];
  /** 超出上限未列出的明细条数 */
  truncated?: number;
}

/** 包的来源（ledger.json 的 source；旧包没有）。 */
export interface ImportSource {
  tenant?: string;
  exported_by?: string;
  app_version?: string;
  deployment?: string;
}

/** 后端可能直接给 source，也可能给整个 ledger.json（{kind, source, scope}），界面两种都认。 */
export type ImportSourcePayload = ImportSource | { kind?: string; source?: ImportSource | null };

/** 包内带登录账号时的说明：只有单账套整套覆盖才恢复（will_restore），合并与 SaaS 只说明不导入。 */
export interface ImportAccountsInfo {
  count: number;
  will_restore: boolean;
  note: string;
}

/** complete 后的预览（dry-run）报告。 */
export interface ImportPreview {
  upload_id: string;
  /** 覆盖模式需要输入的当前账套名称 */
  target_name?: string;
  /** 预览所按的导入方式（切换方式时重新预览） */
  mode?: ImportMode;
  source?: ImportSourcePayload | null;
  items: ImportReportItem[];
  warnings?: string[];
  accounts?: ImportAccountsInfo | null;
}

/** confirm 后的导入任务；done/failed 时带结果报告。 */
export interface ImportJob {
  upload_id: string;
  status: ImportSessionStatus;
  mode: ImportMode;
  /** 0–100；后端给不出时为 null */
  progress?: number | null;
  message?: string;
  error?: string;
  /** 覆盖模式执行前的自动备份文件 */
  backup_file?: string;
  report?: { items: ImportReportItem[]; warnings?: string[]; accounts?: ImportAccountsInfo | null } | null;
}

export interface ImportConfirmInput {
  mode: ImportMode;
  confirm_name?: string;
  /** 合并时是否以导入包的系统设置为准；覆盖模式整体替换，恒为 true */
  include_settings: boolean;
}

/** 预览时总是把系统设置算进去，是否真正导入由确认时的 include_settings 决定。 */
const COMPLETE_BODY = { include_settings: true };

const importPath = (uploadId: string) => `/backup/imports/${encodeURIComponent(uploadId)}`;

export const backupApi = {
  startExport: (includePackages: boolean) =>
    api.post<LedgerExportJob>('/backup/export-tenant', includePackages ? {} : { include_packages: false }),
  exportStatus: (job: string) => api.get<LedgerExportJob>(`/backup/export-tenant/${encodeURIComponent(job)}/status`),
  createImport: (input: ImportUploadInput) => api.post<ImportUpload>('/backup/imports', input),
  /** index 从 0 开始 */
  uploadPart: (uploadId: string, index: number, blob: Blob, signal?: AbortSignal) =>
    request<unknown>(`${importPath(uploadId)}/parts/${index}`, { method: 'PUT', blob, signal }),
  /** mode 省略时按服务端默认（合并）预览；切换到覆盖时带 mode 重新预览 */
  completeImport: (uploadId: string, signal?: AbortSignal, mode?: ImportMode) =>
    request<ImportPreview>(`${importPath(uploadId)}/complete`, {
      method: 'POST',
      json: mode ? { ...COMPLETE_BODY, mode } : COMPLETE_BODY,
      signal,
    }),
  confirmImport: (uploadId: string, input: ImportConfirmInput) =>
    api.post<ImportJob>(`${importPath(uploadId)}/confirm`, input),
  importStatus: (uploadId: string) => api.get<ImportJob>(`${importPath(uploadId)}/status`),
  cancelImport: (uploadId: string) => api.del<unknown>(importPath(uploadId)),
};

export const BACKUP_POLL_MS = 1500;

const isRunning = (status: BackupJobStatus | undefined) => status === 'running';

export interface LedgerExport {
  start: (includePackages: boolean) => void;
  isRunning: boolean;
  job: LedgerExportJob | null;
  error: unknown;
}

/** 备份完成后刷新「服务器上保留的备份」列表（同一任务只刷新一次）。 */
function useRefreshPackagesWhenDone(job: LedgerExportJob | undefined): void {
  const client = useQueryClient();
  const doneJob = job?.status === 'done' ? job.job : null;
  useEffect(() => {
    if (doneJob) void client.invalidateQueries({ queryKey: queryKeys.backupPackages });
  }, [client, doneJob]);
}

/** 一键备份：登记任务后轮询，任务结束自动停止并刷新服务器备份列表；错误由界面就地显示，不弹全局提示。 */
export function useLedgerExport(): LedgerExport {
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: backupApi.startExport,
    onSuccess: (created) => setJobId(created.job),
    meta: { silent: true },
  });
  const status = useQuery({
    queryKey: ['backup', 'export', jobId],
    queryFn: () => backupApi.exportStatus(jobId ?? ''),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (isRunning(query.state.data?.status) ? BACKUP_POLL_MS : false),
    retry: false,
    meta: { silent: true },
  });
  useRefreshPackagesWhenDone(status.data);
  const job = status.data ?? start.data ?? null;
  return {
    start: (includePackages) => {
      setJobId(null);
      start.mutate(includePackages);
    },
    isRunning: start.isPending || isRunning(job?.status),
    job,
    error: start.error ?? status.error,
  };
}

/** 确认导入：错误就地显示。 */
export const useConfirmImport = () =>
  useMutation({
    mutationFn: ({ uploadId, input }: { uploadId: string; input: ImportConfirmInput }) =>
      backupApi.confirmImport(uploadId, input),
    meta: { silent: true },
  });

const isImportFinished = (status: ImportSessionStatus | undefined) => status === 'done' || status === 'failed';

/** 导入任务状态：直到 done/failed 前持续轮询；查询出错即停止，由界面显示原因。 */
export const useImportJob = (uploadId: string | null, enabled: boolean) =>
  useQuery({
    queryKey: ['backup', 'import', uploadId],
    queryFn: () => backupApi.importStatus(uploadId ?? ''),
    enabled: enabled && Boolean(uploadId),
    refetchInterval: (query) =>
      query.state.status !== 'error' && !isImportFinished(query.state.data?.status) ? BACKUP_POLL_MS : false,
    retry: false,
    meta: { silent: true },
  });
