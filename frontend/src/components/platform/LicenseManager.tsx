import { Alert, Badge, Button, CopyButton, Group, Stack, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconCertificate } from '@tabler/icons-react';
import { useState } from 'react';
import {
  useDeleteLicense,
  useLicenseRecords,
  useUnbindLicense,
  useUpdateLicense,
} from '../../api/hooks/platform';
import type { LicenseRecord } from '../../api/types';
import { FormError } from '../settings/users/FormError';
import { LicenseModal } from './LicenseModal';

const INTRO = '授权密钥只在签发时显示一次，列表中只保留前后各 4 位。客户换机时请先解绑实例。';

interface RowHandlers {
  onToggle: (record: LicenseRecord) => void;
  onUnbind: (record: LicenseRecord) => void;
  onDelete: (record: LicenseRecord) => void;
  onEdit: (record: LicenseRecord) => void;
}

function LicenseRow({ record, onToggle, onUnbind, onDelete, onEdit }: RowHandlers & { record: LicenseRecord }) {
  const isActive = record.status === 'active';
  return (
    <Table.Tr data-testid={`license-row-${record.id}`} style={{ opacity: isActive ? 1 : 0.65 }}>
      <Table.Td><Text size="sm" span className="num">{record.license_key}</Text></Table.Td>
      <Table.Td><Text size="sm" truncate maw={160}>{record.customer_name}</Text></Table.Td>
      <Table.Td><Text size="sm" className="num">{record.max_users || '不限'}</Text></Table.Td>
      <Table.Td><Text size="xs" c="dimmed" className="num">{record.valid_until ?? '永久'}</Text></Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={isActive ? 'ink' : 'gray'}>{isActive ? '有效' : '已吊销'}</Badge>
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed" className="num" truncate maw={120}>{record.bound_instance_id || '未绑定'}</Text>
      </Table.Td>
      <Table.Td>
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button size="compact-xs" variant="subtle" aria-label={`编辑授权 ${record.id}`} onClick={() => onEdit(record)}>编辑</Button>
          <Button
            size="compact-xs"
            variant="subtle"
            disabled={!record.bound_instance_id}
            aria-label={`解绑授权 ${record.id}`}
            onClick={() => onUnbind(record)}
          >
            解绑
          </Button>
          <Button size="compact-xs" variant="subtle" color={isActive ? 'red' : undefined} aria-label={`${isActive ? '吊销' : '恢复'}授权 ${record.id}`} onClick={() => onToggle(record)}>
            {isActive ? '吊销' : '恢复'}
          </Button>
          <Button size="compact-xs" variant="subtle" color="red" aria-label={`删除授权 ${record.id}`} onClick={() => onDelete(record)}>删除</Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

function IssuedKey({ record }: { record: LicenseRecord }) {
  return (
    <Alert color="ink" variant="light" title="授权密钥已签发（只显示这一次）">
      <Group gap="sm">
        <Text size="sm" fw={600} className="num" data-testid="issued-license-key">{record.license_key}</Text>
        <CopyButton value={record.license_key}>
          {({ copied, copy }) => (
            <Button size="compact-xs" variant="outline" onClick={copy}>{copied ? '已复制' : '复制'}</Button>
          )}
        </CopyButton>
      </Group>
      <Text size="xs" c="dimmed">请交给客户填入 INVOICE_SORTING_LICENSE_KEY；离开本页后无法再次查看。</Text>
    </Alert>
  );
}

/** 私有化授权记录：签发、改有效期、吊销与恢复、解绑实例、删除。 */
export function LicenseManager() {
  const { data: records = [], isLoading } = useLicenseRecords();
  const update = useUpdateLicense();
  const unbind = useUnbindLicense();
  const remove = useDeleteLicense();
  const [issued, setIssued] = useState<LicenseRecord | null>(null);
  const [editing, setEditing] = useState<LicenseRecord | null>(null);
  const [isIssuing, setIssuing] = useState(false);
  const error = update.error ?? unbind.error ?? remove.error;

  const handlers: RowHandlers = {
    onEdit: setEditing,
    onToggle: (record) =>
      update.mutate({ id: record.id, patch: { status: record.status === 'active' ? 'revoked' : 'active' } }),
    onUnbind: (record) =>
      unbind.mutate(record.id, {
        onSuccess: () => notifications.show({ color: 'ink', message: '已解绑实例，客户可在新机器上重新校验' }),
      }),
    onDelete: (record) => remove.mutate(record.id),
  };

  return (
    <Stack gap="sm">
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed">{INTRO}</Text>
        <Button size="xs" variant="filled" leftSection={<IconCertificate size={14} stroke={1.6} />} onClick={() => setIssuing(true)}>
          签发授权
        </Button>
      </Group>
      {issued && <IssuedKey record={issued} />}
      <FormError error={error} />
      {!isLoading && (
        <div className="table-scroll">
          <Table className="ledger-table" miw={860}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>密钥</Table.Th>
                <Table.Th>客户</Table.Th>
                <Table.Th>用户数</Table.Th>
                <Table.Th>有效期</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>绑定实例</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {records.map((record) => (
                <LicenseRow key={record.id} record={record} {...handlers} />
              ))}
            </Table.Tbody>
          </Table>
        </div>
      )}
      {isIssuing && <LicenseModal onIssued={setIssued} onClose={() => setIssuing(false)} />}
      {editing && <LicenseModal record={editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}
