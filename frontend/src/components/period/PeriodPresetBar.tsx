import { Button, Group } from '@mantine/core';
import { ALL_DATES_LABEL, PERIOD_OPTIONS, type Period, type PeriodPreset } from '../../lib/period';
import './period.css';

interface PeriodPresetBarProps {
  /** 当前预设；custom 时不高亮任何按钮（all 仅在 includeAll 时高亮） */
  value: PeriodPreset;
  onSelect: (period: Period) => void;
  /** 在最前面增加“全部日期”（不限日期）选项，默认不显示 */
  includeAll?: boolean;
}

const ALL_OPTIONS: readonly { value: PeriodPreset; label: string }[] = [
  { value: 'all', label: ALL_DATES_LABEL },
  ...PERIOD_OPTIONS,
];

/** 快捷区间按钮组：窄屏横向滚动，当前预设以 aria-pressed 标示。 */
export function PeriodPresetBar({ value, onSelect, includeAll = false }: PeriodPresetBarProps) {
  const options = includeAll ? ALL_OPTIONS : PERIOD_OPTIONS;
  return (
    <Group gap={4} wrap="nowrap" className="period-presets" role="group" aria-label="快捷区间">
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <Button
            key={option.value}
            size="compact-sm"
            variant={isActive ? 'filled' : 'subtle'}
            color={isActive ? undefined : 'gray'}
            className="period-preset"
            aria-pressed={isActive}
            onClick={() => onSelect({ preset: option.value })}
          >
            {option.label}
          </Button>
        );
      })}
    </Group>
  );
}
