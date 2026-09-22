import { Alert, List, Stack, Text } from '@mantine/core';
import type { ImportPreview } from '../../../api/hooks/backup';
import { formatFileSize } from '../../../lib/fileMeta';
import { packageSource, previewHeadline } from '../../../lib/ledgerTransfer';
import { AccountsNotice } from './AccountsNotice';
import { ImportReportTable } from './ImportReportTable';

function sourceLine(preview: ImportPreview): string {
  const source = packageSource(preview.source);
  if (!source) return '旧版搬迁包（没有来源信息），按整账套包处理';
  const parts = [`来自 ${source.tenant || '未命名账套'}`, source.exported_by && `${source.exported_by}导出`, source.app_version && `v${source.app_version}`];
  return parts.filter(Boolean).join(' · ');
}

interface ImportPreviewViewProps {
  preview: ImportPreview;
  file: File | null;
  /** 正在按新选的导入方式重新生成预览 */
  isRefreshing?: boolean;
}

/** 预览（dry-run）：来源、一句话摘要、分类别明细、登录账号说明与警告。 */
export function ImportPreviewView({ preview, file, isRefreshing = false }: ImportPreviewViewProps) {
  const warnings = preview.warnings ?? [];
  return (
    <Stack gap="xs">
      {file && <Text size="sm">{`${file.name}　${formatFileSize(file.size)}`}</Text>}
      <Text size="xs" c="dimmed">{sourceLine(preview)}</Text>
      <Text size="sm" fw={600}>{previewHeadline(preview.items)}</Text>
      {isRefreshing && <Text size="xs" c="dimmed">正在按所选导入方式重新生成预览…</Text>}
      <ImportReportTable items={preview.items} variant="preview" />
      <AccountsNotice accounts={preview.accounts} />
      {warnings.length > 0 && (
        <Alert color="yellow" variant="light" title="请留意">
          <List size="xs">{warnings.map((warning) => <List.Item key={warning}>{warning}</List.Item>)}</List>
        </Alert>
      )}
    </Stack>
  );
}
