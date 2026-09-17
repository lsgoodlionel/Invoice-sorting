import { Paper, ScrollArea } from '@mantine/core';
import type { UploadItem, UploadStats } from '../../../lib/uploadQueue';
import { UploadFileRow } from './UploadFileRow';
import { UploadSummary } from './UploadSummary';

/** 约 8 行高度，超出后列表内部滚动。 */
const LIST_MAX_HEIGHT = 360;

export interface UploadPanelProps {
  items: readonly UploadItem[];
  stats: UploadStats;
  overallProgress: number;
  isSettled: boolean;
  isFinishing: boolean;
  finishError: string | null;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
  onClear: () => void;
  onRefinish: () => void;
}

/** 拖放区下方的上传面板：汇总 + 每个文件的上传/识别进度。 */
export function UploadPanel({ items, onRetry, onCancel, ...summary }: UploadPanelProps) {
  return (
    <Paper className="upload-panel" radius="sm">
      <UploadSummary {...summary} />
      <ScrollArea.Autosize mah={LIST_MAX_HEIGHT} type="auto">
        <div role="list" aria-label="导入文件列表">
          {items.map((item) => (
            <UploadFileRow key={item.id} item={item} onRetry={onRetry} onCancel={onCancel} />
          ))}
        </div>
      </ScrollArea.Autosize>
    </Paper>
  );
}
