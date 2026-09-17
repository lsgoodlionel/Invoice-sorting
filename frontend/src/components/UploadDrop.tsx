import { Group, Text } from '@mantine/core';
import { Dropzone, type DropzoneProps } from '@mantine/dropzone';
import { IconUpload } from '@tabler/icons-react';

export const ACCEPTED_FILE_TYPES = {
  'application/pdf': ['.pdf'],
  'application/ofd': ['.ofd'],
  'application/octet-stream': ['.ofd'],
  'application/xml': ['.xml'],
  'text/xml': ['.xml'],
  'image/*': ['.png', '.jpg', '.jpeg', '.webp', '.heic'],
};

interface UploadDropProps extends Omit<DropzoneProps, 'onDrop' | 'children'> {
  onFiles: (files: File[]) => void;
  label?: string;
  compact?: boolean;
}

/** 行内小拖放区，用于缺项补传等场景。 */
export function UploadDrop({ onFiles, label = '拖入或点击选择', compact = true, ...rest }: UploadDropProps) {
  return (
    <Dropzone onDrop={onFiles} multiple p={compact ? 4 : 'md'} radius="sm" {...rest}>
      <Group gap={6} justify="center" wrap="nowrap" style={{ pointerEvents: 'none' }}>
        <IconUpload size={14} stroke={1.6} />
        <Text size="xs" c="dimmed">
          {label}
        </Text>
      </Group>
    </Dropzone>
  );
}
