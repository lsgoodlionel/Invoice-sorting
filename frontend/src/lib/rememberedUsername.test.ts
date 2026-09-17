import { afterEach, describe, expect, test, vi } from 'vitest';
import { DEFAULT_USERNAME, REMEMBERED_USERNAME_KEY, loadRememberedUsername, saveRememberedUsername } from './rememberedUsername';

afterEach(() => window.localStorage.clear());

describe('remembered username', () => {
  test('defaults to admin when nothing stored', () => {
    expect(loadRememberedUsername()).toBe(DEFAULT_USERNAME);
    expect(DEFAULT_USERNAME).toBe('admin');
  });

  test('round-trips a saved username', () => {
    saveRememberedUsername('zhangsan');
    expect(window.localStorage.getItem(REMEMBERED_USERNAME_KEY)).toBe('zhangsan');
    expect(loadRememberedUsername()).toBe('zhangsan');
  });

  test('falls back when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => saveRememberedUsername('zhangsan')).not.toThrow();
    expect(loadRememberedUsername()).toBe(DEFAULT_USERNAME);
  });
});
