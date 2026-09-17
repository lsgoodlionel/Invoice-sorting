import { Badge, Text } from '@mantine/core';
import { regionBadge } from '../lib/region';

interface RegionBadgeProps {
  regionName: string;
  isNonlocal: boolean;
  /** 未知地区时显示“—”；为 false 时不渲染 */
  showUnknown?: boolean;
}

/** 开票地区徽标：外地橙色“外地·北京”，本地灰色“上海”，未知“—”。 */
export function RegionBadge({ regionName, isNonlocal, showUnknown = true }: RegionBadgeProps) {
  const meta = regionBadge(regionName, isNonlocal);
  if (!meta) return showUnknown ? <Text span size="xs" c="dimmed">—</Text> : null;
  return (
    <Badge size="sm" radius="xs" variant={isNonlocal ? 'light' : 'outline'} color={meta.color} style={{ flexShrink: 0 }}>
      {meta.label}
    </Badge>
  );
}
