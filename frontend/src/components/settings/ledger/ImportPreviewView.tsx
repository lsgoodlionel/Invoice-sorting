import { Alert, List, Stack, Text } from '@mantine/core';
import type { ImportPreview } from '../../../api/hooks/backup';
import { formatFileSize } from '../../../lib/fileMeta';
import { packageSource, previewHeadline } from '../../../lib/ledgerTransfer';
import { ImportReportTable } from './ImportReportTable';

function sourceLine(preview: ImportPreview): string {
  const source = packageSource(preview.source);
  if (!source) return '旧版搬迁包（没有来源信息），按整账套包处理';
  const parts = [`来自 ${source.tenant || '未命名账套'}`, source.exported_by && `${source.exported_by}导出`, source.app_version && `v${source.app_version}`];
  return parts.filter(Boolean).join(' · ');
}

/** 预览（dry-run）：来源、一句话摘要、分类别明细与警告。 */
export function ImportPreviewView({ preview, file }: { preview: ImportPreview; file: File | null }) {
  const warnings = preview.warnings ?? [];
  return (
    <Stack gap="xs">
      {file && <Text size="sm">{`${file.name}　${formatFileSize(file.size)}`}</Text>}
      <Text size="xs" c="dimmed">{sourceLine(preview)}</Text>
      <Text size="sm" fw={600}>{previewHeadline(preview.items)}</Text>
      <ImportReportTable items={preview.items} variant="preview" />
      {warnings.length > 0 && (
        <Alert color="yellow" variant="light" title="请留意">
          <List size="xs">{warnings.map((warning) => <List.Item key={warning}>{warning}</List.Item>)}</List>
        </Alert>
      )}
    </Stack>
  );
}
