import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, test, vi } from 'vitest';
import type { DateBasis } from '../../api/types';
import { presetRange, resolvePeriod, type Period } from '../../lib/period';
import { renderWithProviders } from '../../test/render';
import { PeriodPresetBar } from './PeriodPresetBar';
import { PeriodRangeText } from './PeriodRangeText';

interface HarnessProps {
  initial: Period;
  onPeriodChange?: (period: Period) => void;
  onDateBasisChange?: (basis: DateBasis) => void;
}

function Harness({ initial, onPeriodChange, onDateBasisChange }: HarnessProps) {
  const [period, setPeriod] = useState<Period>(initial);
  const [basis, setBasis] = useState<DateBasis>('spent');
  const change = (next: Period) => {
    onPeriodChange?.(next);
    setPeriod(next);
  };
  return (
    <>
      <PeriodRangeText
        period={period}
        range={resolvePeriod(period)}
        onPeriodChange={change}
        dateBasis={basis}
        onDateBasisChange={(next) => {
          onDateBasisChange?.(next);
          setBasis(next);
        }}
        verb="统计"
      />
      <PeriodPresetBar value={period.preset} onSelect={change} />
    </>
  );
}

const startInput = () => screen.getByRole('textbox', { name: '起始日期' });
const endInput = () => screen.getByRole('textbox', { name: '结束日期' });
const presetButton = (name: string) => screen.getByRole('button', { name });

async function typeDate(input: HTMLElement, value: string) {
  const user = userEvent.setup();
  await user.clear(input);
  await user.type(input, value);
  fireEvent.blur(input);
}

describe('PeriodPresetBar + PeriodRangeText', () => {
  test('lists quick ranges and highlights the active preset', () => {
    renderWithProviders(<Harness initial={{ preset: 'this_year' }} />);
    const labels = screen.getAllByRole('button').map((button) => button.textContent);
    expect(labels).toEqual(expect.arrayContaining(['本月', '本季度', '本年', '上月', '上季度', '近3年', '近5年', '近10年']));
    expect(screen.queryByRole('button', { name: '全部' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '自定义' })).not.toBeInTheDocument();
    expect(presetButton('本年')).toHaveAttribute('aria-pressed', 'true');
    expect(presetButton('本月')).toHaveAttribute('aria-pressed', 'false');
    const year = presetRange('this_year') ?? { start: '', end: '' };
    expect(startInput()).toHaveValue(year.start);
    expect(endInput()).toHaveValue(year.end);
  });

  test('clicking a preset reports it and shows its resolved dates', async () => {
    const onPeriodChange = vi.fn();
    renderWithProviders(<Harness initial={{ preset: 'this_year' }} onPeriodChange={onPeriodChange} />);
    await userEvent.setup().click(presetButton('近3年'));
    expect(onPeriodChange).toHaveBeenCalledWith({ preset: 'last_3_years' });
    const range = presetRange('last_3_years') ?? { start: '', end: '' };
    await waitFor(() => expect(startInput()).toHaveValue(range.start));
    expect(endInput()).toHaveValue(range.end);
    expect(presetButton('近3年')).toHaveAttribute('aria-pressed', 'true');
  });

  test('typing a date switches to custom and clears preset highlight', async () => {
    const onPeriodChange = vi.fn();
    renderWithProviders(<Harness initial={{ preset: 'this_year' }} onPeriodChange={onPeriodChange} />);
    const year = presetRange('this_year') ?? { start: '', end: '' };
    await typeDate(startInput(), '2026-03-05');
    await waitFor(() =>
      expect(onPeriodChange).toHaveBeenLastCalledWith({ preset: 'custom', start: '2026-03-05', end: year.end }),
    );
    // 半截日期（如 2026-0）不会提交
    expect(onPeriodChange).toHaveBeenCalledTimes(1);
    expect(screen.queryAllByRole('button', { pressed: true })).toHaveLength(0);
  });

  test('picking a day in the calendar sets the end date', async () => {
    const onPeriodChange = vi.fn();
    renderWithProviders(<Harness initial={{ preset: 'custom', start: '2026-02-01', end: '2026-02-10' }} onPeriodChange={onPeriodChange} />);
    const user = userEvent.setup();
    await user.click(endInput());
    await user.click(await screen.findByRole('button', { name: /^20 .*2026$/ }));
    await waitFor(() =>
      expect(onPeriodChange).toHaveBeenLastCalledWith({ preset: 'custom', start: '2026-02-01', end: '2026-02-20' }),
    );
  });

  test('a start later than the end swaps the bounds', async () => {
    const onPeriodChange = vi.fn();
    renderWithProviders(<Harness initial={{ preset: 'custom', start: '2026-02-01', end: '2026-02-10' }} onPeriodChange={onPeriodChange} />);
    await typeDate(startInput(), '2026-05-01');
    await waitFor(() =>
      expect(onPeriodChange).toHaveBeenLastCalledWith({ preset: 'custom', start: '2026-02-10', end: '2026-05-01' }),
    );
    await waitFor(() => expect(startInput()).toHaveValue('2026-02-10'));
    expect(endInput()).toHaveValue('2026-05-01');
  });

  test('legacy all shows 全部日期 with empty bounds', () => {
    renderWithProviders(<Harness initial={{ preset: 'all' }} />);
    expect(screen.getByText('全部日期')).toBeInTheDocument();
    expect(startInput()).toHaveValue('');
    expect(screen.queryAllByRole('button', { pressed: true })).toHaveLength(0);
  });

  test('date basis dropdown reports the new basis', async () => {
    const onDateBasisChange = vi.fn();
    renderWithProviders(<Harness initial={{ preset: 'this_year' }} onDateBasisChange={onDateBasisChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: '日期口径' }));
    await user.click(await screen.findByRole('option', { name: '到账日期' }));
    expect(onDateBasisChange).toHaveBeenCalledWith('received');
  });

  test('includeAll adds a 全部日期 preset that reports all and highlights it', async () => {
    const onSelect = vi.fn();
    const { rerender } = renderWithProviders(<PeriodPresetBar value="this_year" onSelect={onSelect} includeAll />);
    const labels = screen.getAllByRole('button').map((button) => button.textContent);
    expect(labels[0]).toBe('全部日期');
    await userEvent.setup().click(presetButton('全部日期'));
    expect(onSelect).toHaveBeenCalledWith({ preset: 'all' });
    rerender(<PeriodPresetBar value="all" onSelect={onSelect} includeAll />);
    expect(presetButton('全部日期')).toHaveAttribute('aria-pressed', 'true');
    expect(presetButton('本年')).toHaveAttribute('aria-pressed', 'false');
  });

  test('custom basis options replace the default date bases', async () => {
    const onDateBasisChange = vi.fn();
    const options = [
      { value: 'created', label: '创建日期' },
      { value: 'sent', label: '外发日期' },
    ] as const;
    renderWithProviders(
      <PeriodRangeText
        period={{ preset: 'all' }}
        range={{}}
        onPeriodChange={vi.fn()}
        dateBasis="created"
        basisOptions={options}
        onDateBasisChange={onDateBasisChange}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: '日期口径' }));
    expect(screen.queryByRole('option', { name: '支出日期' })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('option', { name: '外发日期' }));
    expect(onDateBasisChange).toHaveBeenCalledWith('sent');
  });
});
