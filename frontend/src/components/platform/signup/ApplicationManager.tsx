import { Group, Pagination, SegmentedControl, Stack, Text, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import type { PlatformApplicationQuery } from '../../../api/hooks/keys';
import { usePlatformApplications } from '../../../api/hooks/platformSignup';
import type { PlatformApplication } from '../../../api/signupTypes';
import { ApplicationDrawer } from './ApplicationDrawer';
import { ApplicationTable } from './ApplicationTable';

type StatusFilter = PlatformApplicationQuery['status'];

const PAGE_SIZE = 20;
const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' },
  { value: 'registered', label: '已注册' },
  { value: 'rejected', label: '已否决' },
  { value: '', label: '全部' },
];
const ALL_VALUE = 'all';

/** 注册申请：按状态筛选、搜索、分页，点开详情抽屉审批。 */
export function ApplicationManager() {
  const [status, setStatus] = useState<StatusFilter>('pending');
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  // 抽屉持有自己的副本：批准后该条会从「待审批」列表消失，但仍需显示手动转告信息
  const [opened, setOpened] = useState<PlatformApplication | null>(null);
  const { data, isLoading } = usePlatformApplications({ status, q: keyword.trim(), page });
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / (data?.page_size ?? PAGE_SIZE)));

  const changeStatus = (value: string) => {
    setStatus(value === ALL_VALUE ? '' : (value as StatusFilter));
    setPage(1);
  };
  const search = (value: string) => {
    setKeyword(value);
    setPage(1);
  };

  return (
    <Stack gap="sm">
      <Group justify="space-between" gap="xs">
        <SegmentedControl
          size="xs"
          aria-label="按状态筛选"
          value={status || ALL_VALUE}
          data={STATUS_OPTIONS.map((option) => ({ value: option.value || ALL_VALUE, label: option.label }))}
          onChange={changeStatus}
        />
        <TextInput size="xs" w={240} placeholder="搜索姓名、邮箱或编号" leftSection={<IconSearch size={14} stroke={1.6} />}
          value={keyword} onChange={(event) => search(event.currentTarget.value)} />
      </Group>
      {!isLoading && data && total > 0 && <ApplicationTable applications={data.items} onOpen={setOpened} />}
      {!isLoading && total === 0 && <Text size="sm" c="dimmed">没有符合条件的申请。</Text>}
      {pages > 1 && <Pagination size="sm" value={page} total={pages} onChange={setPage} />}
      {opened && <ApplicationDrawer application={opened} onClose={() => setOpened(null)} />}
    </Stack>
  );
}
