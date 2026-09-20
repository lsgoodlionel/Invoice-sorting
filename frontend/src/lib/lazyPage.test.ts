import { afterEach, describe, expect, test, vi } from 'vitest';
import { loadWithReload, RELOAD_FLAG_KEY } from './lazyPage';

const reload = vi.fn();

afterEach(() => {
  window.sessionStorage.clear();
  reload.mockClear();
});

function stubReload() {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload },
  });
}

describe('loadWithReload', () => {
  test('returns the module and clears the retry flag on success', async () => {
    window.sessionStorage.setItem(RELOAD_FLAG_KEY, '1');

    const loaded = await loadWithReload(async () => ({ value: 42 }));

    expect(loaded).toEqual({ value: 42 });
    expect(window.sessionStorage.getItem(RELOAD_FLAG_KEY)).toBeNull();
  });

  test('reloads once when a chunk is missing after an upgrade', async () => {
    stubReload();
    let settled = false;

    void loadWithReload(async () => {
      throw new Error('Failed to fetch dynamically imported module');
    }).then(() => {
      settled = true;
    });
    await Promise.resolve();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(RELOAD_FLAG_KEY)).toBe('1');
    expect(settled).toBe(false);
  });

  test('rethrows instead of reloading again when the retry already happened', async () => {
    stubReload();
    window.sessionStorage.setItem(RELOAD_FLAG_KEY, '1');

    await expect(loadWithReload(async () => {
      throw new Error('chunk still missing');
    })).rejects.toThrow('chunk still missing');
    expect(reload).not.toHaveBeenCalled();
  });
});
