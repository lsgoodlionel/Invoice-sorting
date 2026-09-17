import { Button, Group } from '@mantine/core';
import { PERIOD_OPTIONS, type Period, type PeriodPreset } from '../../lib/period';
import './period.css';

interface PeriodPresetBarProps {
  /** 当前预设；custom/all 时不高亮任何按钮 */
  value: PeriodPreset;
  onSelect: (period: Period) => void;
}

/** 快捷区间按钮组：窄屏横向滚动，当前预设以 aria-pressed 标示。 */
export function PeriodPresetBar({ value, onSelect }: PeriodPresetBarProps) {
  return (
    <Group gap={4} wrap="nowrap" className="period-presets" role="group" aria-label="快捷区间">
      {PERIOD_OPTIONS.map((option) => {
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
