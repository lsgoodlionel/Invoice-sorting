import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

/**
 * 升级后浏览器可能仍在用旧的 index.html，去取已被新版本删除的分片，
 * 动态导入会失败、页面卡在加载中。这里失败时自动刷新一次拿新版本；
 * 刷新后仍失败（说明不是版本不一致）就把错误抛给上层，不再循环刷新。
 */
export const RELOAD_FLAG_KEY = 'invoice-sorting:chunk-reloaded';

type Loader<T> = () => Promise<T>;

function readFlag(): boolean {
  try {
    return window.sessionStorage.getItem(RELOAD_FLAG_KEY) === '1';
  } catch {
    return true; // 读不到会话存储时按“已重试过”处理，宁可报错也不反复刷新
  }
}

function writeFlag(value: boolean): void {
  try {
    if (value) window.sessionStorage.setItem(RELOAD_FLAG_KEY, '1');
    else window.sessionStorage.removeItem(RELOAD_FLAG_KEY);
  } catch {
    // 隐私模式下不可写：不影响加载本身
  }
}

export async function loadWithReload<T>(load: Loader<T>): Promise<T> {
  try {
    const loaded = await load();
    writeFlag(false);
    return loaded;
  } catch (error) {
    if (readFlag()) throw error;
    writeFlag(true);
    window.location.reload();
    // 刷新期间保持挂起，避免先闪出错误界面
    return new Promise<T>(() => {});
  }
}

/** 懒加载一个页面组件（具名导出），并带上版本不一致时的自动刷新。 */
export function lazyPage<K extends string, M extends Record<K, ComponentType<object>>>(
  load: Loader<M>,
  name: K,
): LazyExoticComponent<ComponentType<object>> {
  return lazy(() => loadWithReload(load).then((module) => ({ default: module[name] })));
}
