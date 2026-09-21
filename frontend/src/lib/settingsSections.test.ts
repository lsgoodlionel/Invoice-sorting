import { describe, expect, test } from 'vitest';
import { groupSections, resolveSection, visibleSections } from './settingsSections';

describe('settingsSections', () => {
  test('成员看不到管理员分区，推荐好友只在可推荐时出现', () => {
    const member = visibleSections({ isAdmin: false, canRefer: false }).map((s) => s.key);
    expect(member).toEqual(['general', 'categories', 'projects', 'rules', 'security']);

    const referrer = visibleSections({ isAdmin: false, canRefer: true }).map((s) => s.key);
    expect(referrer).toContain('referral');
  });

  test('地址栏分区不存在或无权访问时回到第一个可见分区', () => {
    const sections = visibleSections({ isAdmin: false, canRefer: false });
    expect(resolveSection('users', sections).key).toBe('general');
    expect(resolveSection(null, sections).key).toBe('general');
    expect(resolveSection('projects', sections).key).toBe('projects');
  });

  test('旧地址 ?section=ledger 指向改名后的「备份与搬迁」', () => {
    const sections = visibleSections({ isAdmin: true, canRefer: false });
    expect(resolveSection('ledger', sections).key).toBe('backup');
  });

  test('按组归并且保持顺序', () => {
    const groups = groupSections(visibleSections({ isAdmin: true, canRefer: true }));
    expect(groups.map((g) => g.name)).toEqual(['账本', '成员与账号', '数据与维护']);
    expect(groups[1].sections.map((s) => s.key)).toEqual(['users', 'referral', 'security']);
  });
});
