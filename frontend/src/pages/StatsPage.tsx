import { Button, Group, SegmentedControl, Stack, Text, Title } from '@mantine/core';
import { IconFileSpreadsheet } from '@tabler/icons-react';
import { useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { statsApi, useStats } from '../api/hooks/stats';
import type { DateBasis, StatsGroupBy, StatsQuery } from '../api/types';
import { PeriodPresetBar } from '../components/period/PeriodPresetBar';
import { PeriodRangeText } from '../components/period/PeriodRangeText';
import { MonthTrendChart } from '../components/stats/MonthTrendChart';
import { StatCards } from '../components/stats/StatCards';
import { StatsCrossTable } from '../components/stats/StatsCrossTable';
import { boundedRange, decodePeriod, encodePeriod, formatDataStart, toStatsPeriod, type Period } from '../lib/period';
import { isDateBasis } from '../lib/status';

const GROUP_OPTIONS: { value: StatsGroupBy; label: string }[] = [
  { value: 'category', label: '分类' },
  { value: 'project', label: '项目' },
  { value: 'merchant', label: '商家' },
  { value: 'month', label: '月份' },
];

const isGroupBy = (value: string | null): value is StatsGroupBy => GROUP_OPTIONS.some((o) => o.value === value);

function DataStartHint({ dataStart, start }: { dataStart: string | null | undefined; start: string }) {
  if (!dataStart || dataStart <= start) return null;
  return (
    <Text span size="sm" c="dimmed" className="period-hint">
      （数据自 {formatDataStart(dataStart)} 起）
    </Text>
  );
}

export function StatsPage() {
  const [params, setParams] = useSearchParams();
  const period = toStatsPeriod(decodePeriod(params, 'this_year'));
  const basisParam = params.get('date_basis');
  const dateBasis: DateBasis = isDateBasis(basisParam) ? basisParam : 'spent';
  const groupParam = params.get('group_by');
  const groupBy: StatsGroupBy = isGroupBy(groupParam) ? groupParam : 'category';
  const { start, end } = boundedRange(period);
  const query: StatsQuery = useMemo(() => ({ start, end, date_basis: dateBasis, group_by: groupBy }), [start, end, dateBasis, groupBy]);
  const { data } = useStats(query);

  const patchParams = (patch: Record<string, string>, nextPeriod: Period = period) =>
    setParams(() => {
      const next = encodePeriod(new URLSearchParams(params), nextPeriod);
      Object.entries(patch).forEach(([key, value]) => next.set(key, value));
      return next;
    }, { replace: true });
  const changePeriod = (next: Period) => patchParams({}, next);

  return (
    <Stack gap="lg" className="page">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4} miw={0}>
          <Title order={1} className="page-title">统计</Title>
          <PeriodRangeText
            period={period}
            range={{ start, end }}
            onPeriodChange={changePeriod}
            dateBasis={dateBasis}
            onDateBasisChange={(basis) => patchParams({ date_basis: basis })}
            verb="统计"
            hint={<DataStartHint dataStart={data?.data_start} start={data?.start ?? start} />}
          />
          <PeriodPresetBar value={period.preset} onSelect={changePeriod} />
        </Stack>
        <Button component="a" href={statsApi.exportUrl(query)} variant="outline" leftSection={<IconFileSpreadsheet size={16} />}>
          导出 Excel
        </Button>
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
