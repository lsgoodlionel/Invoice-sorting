import { useEffect } from 'react';

/** 进行中的长任务（上传、导入）期间，关闭或刷新页面前让浏览器弹出确认。 */
export function useBeforeUnloadGuard(isActive: boolean): void {
  useEffect(() => {
    if (!isActive) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // 旧版浏览器需要设置 returnValue 才会提示
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isActive]);
}
