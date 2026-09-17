import { useEffect, useRef, useState } from 'react';

/** 提前加载的视口外边距 */
const ROOT_MARGIN = '120px';

/** 元素首次进入视口后返回 true 并停止观察；不支持 IntersectionObserver 时保持 false。 */
export function useInViewOnce<T extends Element>() {
  const ref = useRef<T | null>(null);
  const [isInView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (isInView || !node || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setInView(true);
        observer.disconnect();
      },
      { rootMargin: ROOT_MARGIN },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [isInView]);

  return { ref, isInView };
}
