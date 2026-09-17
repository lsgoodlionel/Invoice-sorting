import { Text } from '@mantine/core';
import { formatCents } from '../../lib/money';

interface MonthTrendChartProps {
  months: readonly { month: string; amount_cents: number }[];
}

const CHART_HEIGHT = 180;
const LABEL_SPACE = 22;
const BAR_GAP_RATIO = 0.35;

/** 轻量手写 SVG 柱状图：单系列，按月金额。 */
export function MonthTrendChart({ months }: MonthTrendChartProps) {
  if (months.length === 0) return <Text size="sm" c="dimmed">暂无趋势数据。</Text>;
  const max = Math.max(...months.map((m) => m.amount_cents), 1);
  const slot = 100 / months.length;
  const barWidth = slot * (1 - BAR_GAP_RATIO);
  const plotHeight = CHART_HEIGHT - LABEL_SPACE;
  return (
    <svg className="trend-chart" width="100%" height={CHART_HEIGHT} role="img" aria-label="按月支出趋势">
      <line x1="0" x2="100%" y1={plotHeight} y2={plotHeight} stroke="var(--paper-line-strong)" />
      {months.map((item, index) => {
        const height = Math.max((item.amount_cents / max) * (plotHeight - 16), item.amount_cents > 0 ? 2 : 0);
        const x = `${index * slot + (slot - barWidth) / 2}%`;
        return (
          <g key={item.month}>
            <title>{`${item.month}：${formatCents(item.amount_cents)}`}</title>
            <rect x={x} y={plotHeight - height} width={`${barWidth}%`} height={height} fill="var(--accent)" rx="1" />
            <text x={`${index * slot + slot / 2}%`} y={CHART_HEIGHT - 6} textAnchor="middle" fontSize="11" fill="var(--ink-muted)" className="num">
              {item.month.slice(2)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
