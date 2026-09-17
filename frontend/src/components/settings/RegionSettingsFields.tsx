import { Select, SimpleGrid, TagsInput } from '@mantine/core';
import { CHINA_REGIONS } from '../../lib/region';

interface RegionSettingsFieldsProps {
  localRegion: string;
  detailPlatforms: string[];
  onChange: (patch: { localRegion?: string; detailPlatforms?: string[] }) => void;
}

/** 开票地区相关设置：本地地区与已带明细平台。 */
export function RegionSettingsFields({ localRegion, detailPlatforms, onChange }: RegionSettingsFieldsProps) {
  return (
    <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
      <Select
        label="本地地区"
        aria-label="本地地区"
        description="开票地区与此不同的发票标记为外地"
        data={CHINA_REGIONS}
        searchable
        allowDeselect={false}
        value={localRegion}
        onChange={(value) => value && onChange({ localRegion: value })}
      />
      <TagsInput
        label="已带明细平台"
        aria-label="已带明细平台"
        description="外地发票若销售方属于这些平台，不再要求订单截图"
        placeholder="输入平台名后回车"
        value={detailPlatforms}
        onChange={(value) => onChange({ detailPlatforms: value })}
        style={{ gridColumn: 'span 2' }}
      />
    </SimpleGrid>
  );
}
