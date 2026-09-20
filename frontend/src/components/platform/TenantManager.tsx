import { Button, Group, Pagination, Stack, Text, TextInput } from '@mantine/core';
import { IconBuildingStore, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { usePlatformTenants } from '../../api/hooks/platform';
import type { PlatformTenant } from '../../api/types';
import { EditTenantModal } from './EditTenantModal';
import { OpenTenantModal } from './OpenTenantModal';
import { TenantMembersDrawer } from './TenantMembersDrawer';
import { TenantTable } from './TenantTable';

type Dialog =
  | { type: 'open' }
  | { type: 'edit'; tenant: PlatformTenant }
  | { type: 'members'; tenant: PlatformTenant }
  | null;

const PAGE_SIZE = 20;

/** 账套列表：搜索、分页、开通、编辑与成员运营。 */
export function TenantManager() {
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const { data, isLoading } = usePlatformTenants({ q: keyword.trim(), page });
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / (data?.page_size ?? PAGE_SIZE)));

  const search = (value: string) => {
    setKeyword(value);
    setPage(1);
  };

  return (
    <Stack gap="sm">
      <Group justify="space-between" gap="xs">
        <TextInput
          size="xs"
          w={240}
          placeholder="搜索账套标识或名称"
          leftSection={<IconSearch size={14} stroke={1.6} />}
          value={keyword}
          onChange={(event) => search(event.currentTarget.value)}
        />
        <Button
          size="xs"
          variant="filled"
          leftSection={<IconBuildingStore size={14} stroke={1.6} />}
          onClick={() => setDialog({ type: 'open' })}
        >
          开通账套
        </Button>
      </Group>
      {!isLoading && data && (
        <TenantTable
          tenants={data.items}
          onEdit={(tenant) => setDialog({ type: 'edit', tenant })}
          onMembers={(tenant) => setDialog({ type: 'members', tenant })}
        />
      )}
      {!isLoading && total === 0 && <Text size="sm" c="dimmed">没有匹配的账套。</Text>}
      {pages > 1 && <Pagination size="sm" value={page} total={pages} onChange={setPage} />}
      {dialog?.type === 'open' && <OpenTenantModal onClose={close} />}
      {dialog?.type === 'edit' && <EditTenantModal tenant={dialog.tenant} onClose={close} />}
      {dialog?.type === 'members' && <TenantMembersDrawer tenant={dialog.tenant} onClose={close} />}
    </Stack>
  );
}
