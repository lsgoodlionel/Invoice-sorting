import { Chip, Group, SegmentedControl, Stack, Switch, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { CANDIDATE_STATUSES, type CandidateFilters, type EvidenceFilter } from '../../lib/batchCandidates';
import { resolvePeriod } from '../../lib/period';
import { STATUS_META, isStatus } from '../../lib/status';
import { CategorySelect } from '../CategorySelect';
import { PeriodPresetBar } from '../period/PeriodPresetBar';
import { PeriodRangeText } from '../period/PeriodRangeText';
import { ProjectSelect } from '../ProjectSelect';

interface CandidateFilterBarProps {
  filters: CandidateFilters;
  onChange: (patch: Partial<CandidateFilters>) => void;
  /** 批次限定的项目名；null 表示批次未限定项目 */
  batchProjectName: string | null;
  hasProjectLimit: boolean;
}

const EVIDENCE_OPTIONS: { value: EvidenceFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'missing', label: '只看缺凭证' },
  { value: 'complete', label: '只看凭证齐全' },
];

function projectPlaceholder(filters: CandidateFilters, hasProjectLimit: boolean, name: string | null): string {
  return hasProjectLimit && !filters.showAllProjects ? `批次项目：${name ?? '—'}` : '全部项目';
}

function StatusChips({ value, onChange }: { value: CandidateFilters['statuses']; onChange: (patch: Partial<CandidateFilters>) => void }) {
  return (
    <Chip.Group multiple value={[...value]} onChange={(next) => onChange({ statuses: next.filter(isStatus) })}>
      <Group gap={4} role="group" aria-label="状态筛选">
        {CANDIDATE_STATUSES.map((status) => (
          <Chip key={status} value={status} size="xs" variant="outline">{STATUS_META[status].label}</Chip>
        ))}
      </Group>
    </Chip.Group>
  );
}

/** “添加记录”弹窗的筛选区：周期、分类、项目、状态、凭证、搜索。 */
export function CandidateFilterBar({ filters, onChange, batchProjectName, hasProjectLimit }: CandidateFilterBarProps) {
  return (
    <Stack gap={6}>
      <PeriodRangeText
        period={filters.period}
        range={resolvePeriod(filters.period)}
        onPeriodChange={(period) => onChange({ period })}
        dateBasis={filters.dateBasis}
        onDateBasisChange={(dateBasis) => onChange({ dateBasis })}
      />
      <PeriodPresetBar includeAll value={filters.period.preset} onSelect={(period) => onChange({ period })} />
      <Group gap="xs" wrap="wrap" align="center">
        <CategorySelect aria-label="分类筛选" w={140} size="xs" placeholder="全部分类" clearable
          value={filters.categoryId} onChange={(categoryId) => onChange({ categoryId })} />
        <ProjectSelect aria-label="经费项目筛选" w={180} size="xs" creatable={false} clearable
          placeholder={projectPlaceholder(filters, hasProjectLimit, batchProjectName)}
          value={filters.projectId} onChange={(projectId) => onChange({ projectId })} />
        {hasProjectLimit && (
          <Switch size="xs" label="显示全部项目" checked={filters.showAllProjects} disabled={filters.projectId !== null}
            onChange={(event) => onChange({ showAllProjects: event.currentTarget.checked })} />
        )}
      </Group>
      <Group gap="md" wrap="wrap" align="center">
        <StatusChips value={filters.statuses} onChange={onChange} />
        <SegmentedControl size="xs" aria-label="凭证筛选" data={EVIDENCE_OPTIONS} value={filters.evidence}
          onChange={(value) => onChange({ evidence: value as EvidenceFilter })} />
        <TextInput aria-label="搜索记录" placeholder="搜索商家 / 摘要 / 发票号" size="xs" leftSection={<IconSearch size={12} />}
          style={{ flex: 1, minWidth: 180 }} value={filters.search} onChange={(event) => onChange({ search: event.currentTarget.value })} />
      </Group>
    </Stack>
  );
}
