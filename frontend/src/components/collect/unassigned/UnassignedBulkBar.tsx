import { Button, Group, Paper, Text } from '@mantine/core';
import { IconFilePlus, IconLink, IconRefresh, IconTrash } from '@tabler/icons-react';

interface UnassignedBulkBarProps {
  count: number;
  invoiceCount: number;
  primaryVariant: 'filled' | 'light';
  isCreating: boolean;
  isReparsing: boolean;
  isDeleting: boolean;
  onCreate: () => void;
  onAssign: () => void;
  onReparse: () => void;
  onDelete: () => void;
  onClear: () => void;
}

export function UnassignedBulkBar(props: UnassignedBulkBarProps) {
  const hasInvoice = props.invoiceCount > 0;
  return (
    <Paper className="unassigned-bulk-bar" px="md" py="xs" radius={0}>
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text size="sm">已选 {props.count} 个</Text>
          {props.count > props.invoiceCount && hasInvoice && (
            <Text size="xs" c="dimmed">（其中发票 {props.invoiceCount} 个）</Text>
          )}
          <Button size="compact-sm" variant="subtle" onClick={props.onClear}>清除选择</Button>
        </Group>
        <Group gap="xs" wrap="wrap">
          <Button size="sm" variant={props.primaryVariant} leftSection={<IconFilePlus size={14} />} disabled={!hasInvoice} loading={props.isCreating} onClick={props.onCreate}>
            生成记录
          </Button>
          <Button size="sm" variant="outline" leftSection={<IconLink size={14} />} onClick={props.onAssign}>
            归属到记录…
          </Button>
          <Button size="sm" variant="outline" leftSection={<IconRefresh size={14} />} disabled={!hasInvoice} loading={props.isReparsing} onClick={props.onReparse}>
            重新识别
          </Button>
          <Button size="sm" variant="outline" color="red" leftSection={<IconTrash size={14} />} loading={props.isDeleting} onClick={props.onDelete}>
            删除
          </Button>
        </Group>
      </Group>
    </Paper>
  );
}
