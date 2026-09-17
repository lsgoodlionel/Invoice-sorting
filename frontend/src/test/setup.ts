import '@testing-library/jest-dom/vitest';
import { notifications } from '@mantine/notifications';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  // 通知存储是全局的且最多显示 5 条，避免前一个测试的通知把后续通知挤进队列
  notifications.clean();
  notifications.cleanQueue();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const { getComputedStyle } = window;
window.getComputedStyle = (element: Element) => getComputedStyle(element);
window.HTMLElement.prototype.scrollIntoView = () => undefined;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

// jsdom 未实现 document.fonts；Mantine Textarea autosize 会监听字体加载事件
if (!('fonts' in document)) {
  Object.defineProperty(document, 'fonts', {
    configurable: true,
    value: { addEventListener: () => undefined, removeEventListener: () => undefined, ready: Promise.resolve() },
  });
}
