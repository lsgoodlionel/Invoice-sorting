import { Group, Paper, Text } from '@mantine/core';
import { usePlatformOverview } from '../../api/hooks/platform';
import { formatBytes } from '../../lib/platform';

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Paper withBorder radius="sm" px="md" py="xs" style={{ background: 'var(--paper-surface)' }}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="lg" fw={600} className="num">{value}</Text>
    </Paper>
  );
}

/** 概览数字条：账套、活跃账套、账号与最近一次用量快照的合计。 */
export function PlatformOverviewStrip() {
  const { data } = usePlatformOverview(true);
  if (!data) return null;
  return (
    <Group gap="sm" wrap="wrap" data-testid="platform-overview">
      <Metric label="账套" value={String(data.tenants)} />
      <Metric label="启用中" value={String(data.active_tenants)} />
      <Metric label="账号" value={String(data.accounts)} />
      <Metric label="存储合计" value={formatBytes(data.storage_bytes)} />
      <Metric label="记录合计" value={String(data.expenses_created)} />
    </Group>
  );
}
