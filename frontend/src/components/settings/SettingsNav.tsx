import { NativeSelect, NavLink, Stack, Text } from '@mantine/core';
import {
  groupSections,
  type SettingsSectionDef,
  type SettingsSectionKey,
} from '../../lib/settingsSections';

interface SettingsNavProps {
  sections: readonly SettingsSectionDef[];
  active: SettingsSectionKey;
  onSelect: (key: SettingsSectionKey) => void;
}

/** 宽屏：左侧分组导航。 */
export function SettingsSideNav({ sections, active, onSelect }: SettingsNavProps) {
  return (
    <nav aria-label="设置分区" className="settings-nav">
      <Stack gap="md">
        {groupSections(sections).map((group) => (
          <Stack key={group.name} gap={2}>
            <Text className="settings-nav-group">{group.name}</Text>
            {group.sections.map((section) => (
              <NavLink
                key={section.key}
                component="button"
                type="button"
                label={section.label}
                active={section.key === active}
                aria-current={section.key === active ? 'page' : undefined}
                onClick={() => onSelect(section.key)}
                className="settings-nav-link"
              />
            ))}
          </Stack>
        ))}
      </Stack>
    </nav>
  );
}

/** 窄屏：下拉选择分区，省出纵向空间。 */
export function SettingsSelectNav({ sections, active, onSelect }: SettingsNavProps) {
  const data = groupSections(sections).map((group) => ({
    group: group.name,
    items: group.sections.map((section) => ({ value: section.key, label: section.label })),
  }));
  return (
    <NativeSelect
      aria-label="选择设置分区"
      data={data}
      value={active}
      onChange={(event) => onSelect(event.currentTarget.value as SettingsSectionKey)}
    />
  );
}
