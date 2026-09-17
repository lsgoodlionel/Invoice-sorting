import { describe, expect, test, vi } from 'vitest';
import { authEvents } from './authEvents';

describe('authEvents', () => {
  test('notifies subscribers until they unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = authEvents.subscribe(listener);
    authEvents.emitUnauthorized();
    unsubscribe();
    authEvents.emitUnauthorized();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
