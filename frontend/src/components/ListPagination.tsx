import { Button, Group, NumberInput, Pagination, Select, Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import { PAGE_SIZE_OPTIONS, pageCount, type PageSize } from '../lib/pagination';

interface ListPaginationProps {
  total: number;
  page: number;
  pageSize: PageSize;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: PageSize) => void;
  compact?: boolean;
}

const SIZE_DATA = [
  ...PAGE_SIZE_OPTIONS.map((value) => ({ value: String(value), label: `${value} 行` })),
  { value: 'all', label: '全部' },
];

export function ListPagination({ total, page, pageSize, onPageChange, onPageSizeChange, compact = false }: ListPaginationProps) {
  const pages = pageCount(total, pageSize);
  const current = Math.min(page, pages);
  const [jump, setJump] = useState<number | string>(current);
  useEffect(() => setJump(current), [current]);
  const submitJump = () => {
    if (typeof jump === 'number') onPageChange(Math.min(pages, Math.max(1, Math.trunc(jump))));
  };
  return (
    <Group justify="space-between" gap="xs" wrap="wrap" className="list-pagination">
      <Group gap={6}>
        <Text size="xs" c="dimmed">每页显示</Text>
        <Select
          aria-label="每页显示"
          size="xs"
          w={86}
          allowDeselect={false}
          data={SIZE_DATA}
          value={String(pageSize)}
          onChange={(value) => value && onPageSizeChange(value === 'all' ? 'all' : Number(value) as PageSize)}
        />
        <Text size="xs" c="dimmed">共 {total} 条</Text>
      </Group>
      {pageSize !== 'all' && (
        <Group gap={6}>
          <Pagination size="xs" value={current} total={pages} siblings={compact ? 0 : 1} boundaries={1} onChange={onPageChange} />
          {!compact && (
            <>
              <NumberInput aria-label="跳转页码" size="xs" w={72} min={1} max={pages} allowDecimal={false} value={jump} onChange={setJump} onKeyDown={(event) => event.key === 'Enter' && submitJump()} />
              <Button size="xs" variant="default" onClick={submitJump}>跳转</Button>
            </>
          )}
        </Group>
      )}
    </Group>
  );
}
