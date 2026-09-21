import { Anchor, Badge, Button, Group, Stack, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconDatabase, IconDownload } from '@tabler/icons-react';
import {
  snapshotDownloadUrl,
  useCreateSnapshot,
  useDatabaseSnapshots,
  type DatabaseSnapshot,
} from '../../../api/hooks/backup-snapshots';
import { formatFileSize } from '../../../lib/fileMeta';

const KIND_LABEL: Record<DatabaseSnapshot['kind'], string> = { manual: '手动', upgrade: '升级前自动' };

function formatTime(value: string): string {
  return value.slice(0, 16).replace('T', ' ');
}

function SnapshotTable({ snapshots }: { snapshots: readonly DatabaseSnapshot[] }) {
  if (snapshots.length === 0) return <Text size="sm" c="dimmed">还没有快照。</Text>;
  return (
    <Table className="ledger-table" aria-label="数据库快照">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>时间</Table.Th>
          <Table.Th>来源</Table.Th>
          <Table.Th ta="right">大小</Table.Th>
          <Table.Th />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {snapshots.map((snapshot) => (
          <Table.Tr key={snapshot.name}>
            <Table.Td className="num">{formatTime(snapshot.created_at)}</Table.Td>
            <Table.Td><Badge variant="light" color={snapshot.kind === 'manual' ? 'ink' : 'gray'}>{KIND_LABEL[snapshot.kind]}</Badge></Table.Td>
            <Table.Td ta="right" className="num">{formatFileSize(snapshot.size)}</Table.Td>
            <Table.Td ta="right">
              <Anchor href={snapshotDownloadUrl(snapshot.name)} download={snapshot.name} size="sm" aria-label={`下载快照 ${snapshot.name}`}>
                <Group gap={4} wrap="nowrap"><IconDownload size={14} />下载</Group>
              </Anchor>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

/** 数据库快照：只含记录数据库、不含附件，保留在服务器上，用于做有风险的操作前留底。 */
export function SnapshotPanel() {
  const { data: snapshots = [] } = useDatabaseSnapshots();
  const create = useCreateSnapshot();
  const submit = () =>
    create.mutate(undefined, {
      onSuccess: (result) => notifications.show({ color: 'ink', title: '已创建数据库快照', message: result.name }),
    });

  return (
    <Stack gap="sm">
      <Text fw={600}>数据库快照</Text>
      <Text size="sm" c="dimmed">
        只保存记录数据库（记录、分类、规则、批次、时间线），<b>不含发票和凭证附件</b>，保存在服务器上（保留最近 10 份）。
        适合在批量改分类、导入别人的账本等操作前先留个底；硬盘损坏时它会和原数据一起丢失，不能替代完整备份。
        每次升级前系统也会自动留一份。
      </Text>
      <Group>
        <Button variant="outline" leftSection={<IconDatabase size={16} />} loading={create.isPending} onClick={submit}>
          创建数据库快照
        </Button>
      </Group>
      <SnapshotTable snapshots={snapshots} />
    </Stack>
  );
}
