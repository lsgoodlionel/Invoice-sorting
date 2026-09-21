/** 设置页分区：按用途分组，左侧导航一次只显示一个分区。 */

export type SettingsSectionKey =
  | 'general'
  | 'categories'
  | 'projects'
  | 'rules'
  | 'reclassify'
  | 'users'
  | 'referral'
  | 'security'
  | 'backup'
  | 'diagnostics';

export interface SettingsAccess {
  isAdmin: boolean;
  canRefer: boolean;
}

export interface SettingsSectionDef {
  key: SettingsSectionKey;
  label: string;
  group: string;
  description: string;
  /** 所有人可见，但只有管理员能修改 */
  isAdminEditable?: boolean;
  isVisible: (access: SettingsAccess) => boolean;
}

const EVERYONE = () => true;
const ADMIN_ONLY = (access: SettingsAccess) => access.isAdmin;

export const SETTINGS_SECTIONS: readonly SettingsSectionDef[] = [
  { key: 'general', label: '基本', group: '账本', isAdminEditable: true, isVisible: EVERYONE,
    description: '报销抬头、本地地区、提醒天数与数据目录。备份在「数据与维护 → 备份与搬迁」。' },
  { key: 'categories', label: '分类', group: '账本', isAdminEditable: true, isVisible: EVERYONE,
    description: '支出分类与自动归类的关键词。' },
  { key: 'projects', label: '经费项目', group: '账本', isVisible: EVERYONE,
    description: '经费号与项目，记录和批次可按项目归集。' },
  { key: 'rules', label: '凭证清单规则', group: '账本', isAdminEditable: true, isVisible: EVERYONE,
    description: '每类支出需要准备哪些材料。' },
  { key: 'reclassify', label: '分类整理', group: '账本', isVisible: ADMIN_ONLY,
    description: '按最新规则检查已有记录的分类，确认后批量改正。' },
  { key: 'users', label: '用户管理', group: '成员与账号', isVisible: ADMIN_ONLY,
    description: '添加成员、调整角色、停用与重置密码。' },
  { key: 'referral', label: '推荐好友', group: '成员与账号', isVisible: (access) => access.canRefer,
    description: '分享你的推荐链接，好友注册后获得独立账本。' },
  { key: 'security', label: '登录与安全', group: '成员与账号', isVisible: EVERYONE,
    description: '修改自己的登录密码。' },
  { key: 'backup', label: '备份与搬迁', group: '数据与维护', isVisible: ADMIN_ONLY,
    description: '完整备份下载到本机、服务器上的数据库快照，以及从导出包导入。' },
  { key: 'diagnostics', label: '运行日志与诊断', group: '数据与维护', isVisible: ADMIN_ONLY,
    description: '服务出问题时生成脱敏诊断包交给开发。' },
];

export function visibleSections(access: SettingsAccess): SettingsSectionDef[] {
  return SETTINGS_SECTIONS.filter((section) => section.isVisible(access));
}

/** 改名前的旧分区地址，继续指向新分区（书签与已分享的链接不失效）。 */
const SECTION_ALIASES: Readonly<Record<string, SettingsSectionKey>> = { ledger: 'backup' };

/** 地址栏里的分区不存在或无权查看时，回到第一个可见分区。 */
export function resolveSection(requested: string | null, sections: readonly SettingsSectionDef[]): SettingsSectionDef {
  const key = requested ? (SECTION_ALIASES[requested] ?? requested) : null;
  return sections.find((section) => section.key === key) ?? sections[0];
}

export interface SettingsGroup {
  name: string;
  sections: SettingsSectionDef[];
}

export function groupSections(sections: readonly SettingsSectionDef[]): SettingsGroup[] {
  return sections.reduce<SettingsGroup[]>((groups, section) => {
    const last = groups.at(-1);
    if (last && last.name === section.group) {
      return [...groups.slice(0, -1), { ...last, sections: [...last.sections, section] }];
    }
    return [...groups, { name: section.group, sections: [section] }];
  }, []);
}
