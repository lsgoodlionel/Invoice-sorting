// 账本搬迁界面用到的纯函数：报告文案、搬迁包校验、只读判断。
import type { ImportReportItem, ImportReportKey, ImportSource, ImportSourcePayload } from '../api/hooks/backup';
import type { LicenseStatus, QuotaStatus } from '../api/types';

/** 设计文档第 8 节：单包上限 2 GB */
export const MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024;

/** 后端未给 label 时的兜底名称 */
const REPORT_LABELS: Readonly<Record<string, string>> = {
  records: '记录',
  attachments: '附件',
  users: '用户',
  categories: '分类',
  projects: '经费项目',
  rules: '凭证规则',
  memories: '分类记忆',
  batches: '批次',
  exports: '资料包生成记录',
  settings: '系统设置',
};

export const reportLabel = (item: Pick<ImportReportItem, 'key' | 'label'>): string =>
  item.label || REPORT_LABELS[item.key] || item.key;

/** 取包的来源：兼容直接给 source 与给整个 ledger.json 两种形状；旧包返回 null。 */
export function packageSource(payload: ImportSourcePayload | null | undefined): ImportSource | null {
  if (!payload) return null;
  const source = 'kind' in payload || 'source' in payload ? (payload as { source?: ImportSource | null }).source : (payload as ImportSource);
  return source && (source.tenant || source.exported_by || source.app_version) ? source : null;
}

const sumOf = (items: readonly ImportReportItem[], pick: (item: ImportReportItem) => number) =>
  items.reduce((total, item) => total + pick(item), 0);

const addedOf = (items: readonly ImportReportItem[], key: ImportReportKey) =>
  items.find((item) => item.key === key)?.added ?? 0;

/** 预览一句话：将新增多少记录/附件、跳过多少重复、多少冲突。 */
export function previewHeadline(items: readonly ImportReportItem[]): string {
  const skipped = sumOf(items, (item) => item.skipped);
  const conflicts = sumOf(items, (item) => item.conflicts);
  const base = `将新增 ${addedOf(items, 'records')} 条记录、${addedOf(items, 'attachments')} 个附件，跳过 ${skipped} 项重复`;
  return conflicts > 0 ? `${base}，${conflicts} 项冲突需要留意` : base;
}

/** 选择的文件不能导入时返回原因。 */
export function packageFileError(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.zip')) return '只能导入 .zip 搬迁包';
  if (file.size <= 0) return '文件是空的';
  if (file.size > MAX_PACKAGE_BYTES) return '搬迁包超过 2 GB，请在服务器上用命令行 import-tenant 导入';
  return null;
}

/** 授权失效或账套停用（只读）时不能导入，返回可展示的原因。 */
export function importBlockReason(license: LicenseStatus | undefined, quota: QuotaStatus | undefined): string | null {
  if (license?.state === 'readonly') return license.message || '授权已失效，账本处于只读状态';
  if (quota?.is_readonly) return quota.readonly_message || '账套已停用，处于只读状态';
  return null;
}
