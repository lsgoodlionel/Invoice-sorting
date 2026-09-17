import { Button, Group, SegmentedControl, Stack, Text, Title } from '@mantine/core';
import { IconFileSpreadsheet } from '@tabler/icons-react';
import { useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { statsApi, useStats } from '../api/hooks/stats';
import type { DateBasis, StatsGroupBy, StatsQuery } from '../api/types';
import { PeriodPicker } from '../components/PeriodPicker';
import { MonthTrendChart } from '../components/stats/MonthTrendChart';
import { StatCards } from '../components/stats/StatCards';
import { StatsCrossTable } from '../components/stats/StatsCrossTable';
import { decodePeriod, encodePeriod, presetRange, resolvePeriod, type Period } from '../lib/period';
import { DATE_BASIS_OPTIONS, isDateBasis } from '../lib/status';

const GROUP_OPTIONS: { value: StatsGroupBy; label: string }[] = [
  { value: 'category', label: '分类' },
  { value: 'project', label: '项目' },
  { value: 'merchant', label: '商家' },
  { value: 'month', label: '月份' },
];

const isGroupBy = (value: string | null): value is StatsGroupBy => GROUP_OPTIONS.some((o) => o.value === value);

/** 统计接口需要明确起止；“全部”或未填完的自定义区间回退为本年。 */
function toStatsRange(period: Period): { start: string; end: string } {
  const range = resolvePeriod(period);
  const fallback = presetRange('this_year') as { start: string; end: string };
  return { start: range.start ?? '2000-01-01', end: range.end ?? fallback.end };
}

export function StatsPage() {
  const [params, setParams] = useSearchParams();
  const period = decodePeriod(params, 'this_year');
  const basisParam = params.get('date_basis');
  const dateBasis: DateBasis = isDateBasis(basisParam) ? basisParam : 'spent';
  const groupParam = params.get('group_by');
  const groupBy: StatsGroupBy = isGroupBy(groupParam) ? groupParam : 'category';
  const { start, end } = toStatsRange(period);
  const query: StatsQuery = useMemo(() => ({ start, end, date_basis: dateBasis, group_by: groupBy }), [start, end, dateBasis, groupBy]);
  const { data } = useStats(query);

  const patchParams = (patch: Record<string, string>, nextPeriod: Period = period) =>
    setParams(() => {
      const next = encodePeriod(new URLSearchParams(params), nextPeriod);
      Object.entries(patch).forEach(([key, value]) => next.set(key, value));
      return next;
    }, { replace: true });

  const basisLabel = DATE_BASIS_OPTIONS.find((option) => option.value === dateBasis)?.label;

  return (
    <Stack gap="lg" className="page">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={1} className="page-title">统计</Title>
          <Text size="sm" c="dimmed" className="num">按{basisLabel}统计 · {start} 至 {end}</Text>
        </div>
        <Group gap="xs">
          <PeriodPicker
            period={period}
            onPeriodChange={(next) => patchParams({}, next)}
            dateBasis={dateBasis}
            onDateBasisChange={(basis) => patchParams({ date_basis: basis })}
          />
          <Button component="a" href={statsApi.exportUrl(query)} variant="outline" leftSection={<IconFileSpreadsheet size={16} />}>
            导出 Excel
          </Button>
        </Group>
      </Group>
      {data && <StatCards totals={data.totals} />}
      <Stack gap="xs">
        <Group justify="space-between">
          <Text className="section-label">交叉汇总（点击金额查看记录）</Text>
          <SegmentedControl size="xs" data={GROUP_OPTIONS} value={groupBy} onChange={(value) => patchParams({ group_by: value })} />
        </Group>
        {data && <StatsCrossTable rows={data.rows} start={data.start} end={data.end} dateBasis={dateBasis} groupBy={groupBy} />}
      </Stack>
      <Stack gap="xs">
        <Text className="section-label">按月趋势</Text>
        {data && <MonthTrendChart months={data.months} />}
      </Stack>
    </Stack>
  );
}
