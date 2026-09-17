import { Button, Group, Stack, Text } from '@mantine/core';
import { IconFilePlus } from '@tabler/icons-react';

const EXPLANATION =
  '待归属 = 已导入但还没挂到任何支出记录的文件（跳过确认的发票、订单截图、支付记录等）。发票可一键生成记录；其他文件请归属到对应记录。';

interface UnassignedHeaderProps {
  total: number;
  invoiceCount: number;
  isCreating: boolean;
  onCreateAll: () => void;
}

export function UnassignedHeader({ total, invoiceCount, isCreating, onCreateAll }: UnassignedHeaderProps) {
  return (
    <Group justify="space-between" align="flex-start" wrap="nowrap">
      <Stack gap={2}>
        <Text className="section-label">待归属附件 {total}</Text>
        <Text size="xs" c="dimmed">{EXPLANATION}</Text>
      </Stack>
      {invoiceCount > 0 && (
        <Button size="xs" variant="outline" leftSection={<IconFilePlus size={14} />} loading={isCreating} onClick={onCreateAll} style={{ flexShrink: 0 }}>
          全部发票生成记录（{invoiceCount}）
        </Button>
      )}
    </Group>
  );
}
