import { Badge, Button, Group, Table, Text } from '@mantine/core';
import type { PlatformTenant } from '../../api/types';
import { TENANT_STATUS_COLORS, formatBytes, tenantStatusLabel } from '../../lib/platform';

const TABLE_MIN_WIDTH = 900;

export interface TenantRowHandlers {
  onEdit: (tenant: PlatformTenant) => void;
  onMembers: (tenant: PlatformTenant) => void;
}

function UsageCell({ tenant }: { tenant: PlatformTenant }) {
  if (!tenant.usage) return <Text size="xs" c="dimmed">—</Text>;
  return (
    <Text size="xs" c="dimmed" className="num">
      {formatBytes(tenant.usage.storage_bytes)} · {tenant.usage.expenses_created} 条
    </Text>
  );
}

function TenantRow({ tenant, onEdit, onMembers }: TenantRowHandlers & { tenant: PlatformTenant }) {
  const isActive = tenant.status === 'active';
  return (
    <Table.Tr data-testid={`tenant-row-${tenant.slug}`} style={{ opacity: isActive ? 1 : 0.65 }}>
      <Table.Td><Text size="sm" span className="num">{tenant.slug}</Text></Table.Td>
      <Table.Td><Text size="sm" truncate maw={180}>{tenant.name}</Text></Table.Td>
      <Table.Td>
        <Text size="sm">{tenant.plan?.name ?? '未指定'}</Text>
      </Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={TENANT_STATUS_COLORS[tenant.status]}>
          {tenantStatusLabel(tenant.status)}
        </Badge>
      </Table.Td>
      <Table.Td><Text size="sm" className="num">{tenant.member_count}</Text></Table.Td>
      <Table.Td><UsageCell tenant={tenant} /></Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed" className="num">{tenant.expires_on ?? '永久'}</Text>
      </Table.Td>
      <Table.Td>
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <Button size="compact-xs" variant="subtle" aria-label={`管理 ${tenant.slug} 的成员`} onClick={() => onMembers(tenant)}>
            成员
          </Button>
          <Button size="compact-xs" variant="subtle" aria-label={`编辑 ${tenant.slug}`} onClick={() => onEdit(tenant)}>
            编辑
          </Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

export function TenantTable({ tenants, ...handlers }: TenantRowHandlers & { tenants: readonly PlatformTenant[] }) {
  return (
    <div className="table-scroll">
      <Table className="ledger-table" miw={TABLE_MIN_WIDTH}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>标识</Table.Th>
            <Table.Th>名称</Table.Th>
            <Table.Th>套餐</Table.Th>
            <Table.Th>状态</Table.Th>
            <Table.Th>成员</Table.Th>
            <Table.Th>用量</Table.Th>
            <Table.Th>到期</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tenants.map((tenant) => (
            <TenantRow key={tenant.slug} tenant={tenant} {...handlers} />
          ))}
        </Table.Tbody>
      </Table>
    </div>
  );
}
