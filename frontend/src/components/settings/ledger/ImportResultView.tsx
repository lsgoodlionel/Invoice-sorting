import { Alert, Button, Stack, Text } from '@mantine/core';
import type { ImportJob } from '../../../api/hooks/backup';
import { AccountsNotice } from './AccountsNotice';
import { ImportReportTable } from './ImportReportTable';

/** 导入完成：结果报告（可展开明细），覆盖模式附自动备份位置。 */
export function ImportResultView({ job, onFinish }: { job: ImportJob; onFinish: () => void }) {
  const items = job.report?.items ?? [];
  const warnings = job.report?.warnings ?? [];
  return (
    <Stack gap="xs">
      <Alert color="ink" variant="light" title="导入完成">
        {job.mode === 'replace' ? '当前账本已替换为搬迁包内容。' : '搬迁包内容已并入当前账本，已有记录未作改动。'}
        {job.backup_file && ` 导入前的自动备份：${job.backup_file}`}
      </Alert>
      {items.length > 0 && <ImportReportTable items={items} variant="result" />}
      <AccountsNotice accounts={job.report?.accounts} isResult />
      {warnings.map((warning) => <Text key={warning} size="xs" c="dimmed">{warning}</Text>)}
      <Button variant="outline" onClick={onFinish} style={{ alignSelf: 'flex-start' }}>完成</Button>
    </Stack>
  );
}
