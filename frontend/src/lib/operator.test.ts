import { describe, expect, test } from 'vitest';
import { eventActorLabel, uploaderName } from './operator';

describe('uploaderName', () => {
  test('shows uploader or inbox', () => {
    expect(uploaderName({ id: 2, display_name: '张三' })).toBe('张三');
    expect(uploaderName(null)).toBe('收件箱');
  });
});

describe('eventActorLabel', () => {
  test('uses actor, system for automatic events without actor, nothing for manual', () => {
    expect(eventActorLabel({ actor: { id: 2, display_name: '张三' }, is_manual: false })).toBe('张三');
    expect(eventActorLabel({ actor: null, is_manual: false })).toBe('系统');
    expect(eventActorLabel({ actor: null, is_manual: true })).toBeNull();
  });
});
