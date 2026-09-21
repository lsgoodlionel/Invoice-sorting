import { Anchor, Group, Table, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import type { BackupFile } from '../api/hooks/backupPackages';
import { formatFileSize } from '../lib/fileMeta';
import { formatDateTime } from '../lib/signup';

interface BackupFileTableProps {
  files: readonly BackupFile[];
  /** 表格的无障碍名称 */
  label: string;
  emptyText: string;
  downloadUrl: (name: string) => string;
}

/** 服务器上保留的备份：时间、大小、下载（账套备份与平台备份共用）。 */
export function BackupFileTable({ files, label, emptyText, downloadUrl }: BackupFileTableProps) {
  if (files.length === 0) return <Text size="sm" c="dimmed">{emptyText}</Text>;
  return (
    <Table className="ledger-table" aria-label={label}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>时间</Table.Th>
          <Table.Th>文件</Table.Th>
          <Table.Th ta="right">大小</Table.Th>
          <Table.Th />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {files.map((file) => (
          <Table.Tr key={file.name}>
            <Table.Td className="num">{formatDateTime(file.created_at)}</Table.Td>
            <Table.Td><Text size="xs" c="dimmed">{file.name}</Text></Table.Td>
            <Table.Td ta="right" className="num">{formatFileSize(file.size)}</Table.Td>
            <Table.Td ta="right">
              <Anchor href={downloadUrl(file.name)} download={file.name} size="sm" aria-label={`下载 ${file.name}`}>
                <Group gap={4} wrap="nowrap"><IconDownload size={14} />下载</Group>
              </Anchor>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
