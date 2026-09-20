import { Button, Menu, Text } from '@mantine/core';
import { IconCheck, IconChevronRight, IconSwitchHorizontal } from '@tabler/icons-react';
import { useAccountTenants, useAuthStatus, useSwitchTenant } from '../../api/hooks/auth';

const MIN_TENANTS_TO_SWITCH = 2;

/**
 * 侧边栏底部的账套切换入口。
 * 只在多租户部署、且当前账号有两个以上账套时出现；单租户部署完全不渲染。
 */
export function TenantSwitcher() {
  const { data: status } = useAuthStatus();
  const isMultiTenant = Boolean(status?.multi_tenant);
  const { data: tenants = [] } = useAccountTenants(isMultiTenant);
  const switchTenant = useSwitchTenant();

  if (!isMultiTenant || tenants.length < MIN_TENANTS_TO_SWITCH) return null;
  const current = tenants.find((tenant) => tenant.is_current) ?? null;

  return (
    <Menu position="right-end" withArrow shadow="sm" width={220}>
      <Menu.Target>
        <Button
          variant="subtle"
          color="gray"
          size="xs"
          justify="space-between"
          className="nav-tenant"
          loading={switchTenant.isPending}
          leftSection={<IconSwitchHorizontal size={16} stroke={1.6} />}
          rightSection={<IconChevronRight size={14} stroke={1.6} />}
          data-testid="tenant-switcher"
        >
          {current?.name ?? '选择账套'}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>切换账套</Menu.Label>
        {tenants.map((tenant) => (
          <Menu.Item
            key={tenant.slug}
            disabled={tenant.is_current}
            leftSection={tenant.is_current ? <IconCheck size={14} stroke={1.8} /> : null}
            onClick={() => switchTenant.mutate(tenant.slug)}
          >
            <Text size="sm" truncate>{tenant.name}</Text>
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
