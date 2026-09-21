import { Badge, Button, Table, Text } from '@mantine/core';
import type { PlatformApplication } from '../../../api/signupTypes';
import { APPLICATION_STATUS_COLORS, APPLICATION_STATUS_LABELS, formatDateTime } from '../../../lib/signup';

const TABLE_MIN_WIDTH = 860;

interface ApplicationTableProps {
  applications: readonly PlatformApplication[];
  onOpen: (application: PlatformApplication) => void;
}

function ApplicationRow({ application, onOpen }: { application: PlatformApplication; onOpen: ApplicationTableProps['onOpen'] }) {
  return (
    <Table.Tr data-testid={`application-row-${application.id}`}>
      <Table.Td><Text size="sm" className="num">{application.number}</Text></Table.Td>
      <Table.Td><Text size="sm">{application.name}</Text></Table.Td>
      <Table.Td><Text size="sm" className="num" truncate maw={220}>{application.email}</Text></Table.Td>
      <Table.Td><Text size="sm" truncate maw={180}>{application.identity}</Text></Table.Td>
      <Table.Td><Text size="sm">{application.referrer?.display_name ?? '—'}</Text></Table.Td>
      <Table.Td><Text size="xs" c="dimmed" className="num">{formatDateTime(application.created_at)}</Text></Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={APPLICATION_STATUS_COLORS[application.status]}>
          {APPLICATION_STATUS_LABELS[application.status]}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Button size="compact-xs" variant="subtle" aria-label={`查看申请 ${application.number}`} onClick={() => onOpen(application)}>
          查看
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

export function ApplicationTable({ applications, onOpen }: ApplicationTableProps) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>编号</Table.Th>
            <Table.Th>姓名</Table.Th>
            <Table.Th>邮箱</Table.Th>
            <Table.Th>单位或身份</Table.Th>
            <Table.Th>推荐人</Table.Th>
            <Table.Th>提交时间</Table.Th>
            <Table.Th>状态</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {applications.map((application) => (
            <ApplicationRow key={application.id} application={application} onOpen={onOpen} />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
