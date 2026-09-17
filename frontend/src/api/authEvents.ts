// 认证失效事件：受保护请求返回 401 时发布，AuthGate 订阅后刷新认证状态。
type Listener = () => void;

let listeners: readonly Listener[] = [];

export const authEvents = {
  subscribe(listener: Listener): () => void {
    listeners = [...listeners, listener];
    return () => {
      listeners = listeners.filter((item) => item !== listener);
    };
  },
  emitUnauthorized(): void {
    listeners.forEach((listener) => listener());
  },
};
