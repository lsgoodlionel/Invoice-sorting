import { useEffect, useRef, useState, type DragEvent } from 'react';

function hasFiles(dataTransfer: DataTransfer | null): boolean {
  return Array.from(dataTransfer?.types ?? []).includes('Files');
}

/** 原生拖放目标：拖入文件时 isOver=true（处理子元素进出抖动），松开回调文件列表。 */
export function useFileDropTarget(onFiles: (files: File[]) => void) {
  const depthRef = useRef(0);
  const [isOver, setOver] = useState(false);

  const reset = () => {
    depthRef.current = 0;
    setOver(false);
  };

  const handlers = {
    onDragEnter: (event: DragEvent<HTMLElement>) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      depthRef.current += 1;
      setOver(true);
    },
    onDragOver: (event: DragEvent<HTMLElement>) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
    },
    onDragLeave: (event: DragEvent<HTMLElement>) => {
      if (!hasFiles(event.dataTransfer)) return;
      depthRef.current = Math.max(0, depthRef.current - 1);
      if (depthRef.current === 0) setOver(false);
    },
    onDrop: (event: DragEvent<HTMLElement>) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      event.stopPropagation();
      reset();
      const files = Array.from(event.dataTransfer.files);
      if (files.length > 0) onFiles(files);
    },
  };

  return { isOver, handlers };
}

function preventFileDefault(event: globalThis.DragEvent) {
  if (hasFiles(event.dataTransfer)) event.preventDefault();
}

/** 页面级：文件拖到非目标区域时阻止浏览器直接打开文件。 */
export function usePreventFileDrop(): void {
  useEffect(() => {
    window.addEventListener('dragover', preventFileDefault);
    window.addEventListener('drop', preventFileDefault);
    return () => {
      window.removeEventListener('dragover', preventFileDefault);
      window.removeEventListener('drop', preventFileDefault);
    };
  }, []);
}
