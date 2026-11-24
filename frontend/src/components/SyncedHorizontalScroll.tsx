import { useRef, type ReactNode, type UIEvent } from 'react';

export function SyncedHorizontalScroll({ contentWidth, children }: { contentWidth: number; children: ReactNode }) {
  const topRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const sync = (source: 'top' | 'body', event: UIEvent<HTMLDivElement>) => {
    const target = source === 'top' ? bodyRef.current : topRef.current;
    if (target && target.scrollLeft !== event.currentTarget.scrollLeft) target.scrollLeft = event.currentTarget.scrollLeft;
  };
  return (
    <div className="table-scroll-shell">
      <div ref={topRef} className="table-scroll table-scroll-top" aria-label="横向滚动工具" onScroll={(event) => sync('top', event)}>
        <div style={{ width: contentWidth, height: 1 }} />
      </div>
      <div ref={bodyRef} className="table-scroll" onScroll={(event) => sync('body', event)}>{children}</div>
    </div>
  );
}
