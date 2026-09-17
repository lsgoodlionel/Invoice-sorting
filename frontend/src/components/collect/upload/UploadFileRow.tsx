import { ActionIcon, Text, Tooltip } from '@mantine/core';
import { IconX } from '@tabler/icons-react';
import { formatFileSize, middleEllipsis } from '../../../lib/fileMeta';
import { isActivePhase, type UploadItem } from '../../../lib/uploadQueue';
import { FileTypeIcon } from './FileTypeIcon';
import { UploadFileStatus } from './UploadFileStatus';

const NAME_MAX_CHARS = 36;

interface UploadFileRowProps {
  item: UploadItem;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
}

export function UploadFileRow({ item, onRetry, onCancel }: UploadFileRowProps) {
  return (
    <div role="listitem" aria-label={item.name} className="upload-row" data-phase={item.phase}>
      <FileTypeIcon name={item.name} mime={item.file.type} />
      <Text size="sm" className="upload-row-name" title={item.name}>{middleEllipsis(item.name, NAME_MAX_CHARS)}</Text>
      <Text size="xs" c="dimmed" className="num upload-row-size">{formatFileSize(item.size)}</Text>
      <div className="upload-row-status"><UploadFileStatus item={item} onRetry={onRetry} /></div>
      <div className="upload-row-action">
        {isActivePhase(item.phase) && (
          <Tooltip label="取消">
            <ActionIcon variant="subtle" color="paper.7" size="sm" aria-label={`取消 ${item.name}`} onClick={() => onCancel(item.id)}>
              <IconX size={14} />
            </ActionIcon>
          </Tooltip>
        )}
      </div>
    </div>
  );
}
