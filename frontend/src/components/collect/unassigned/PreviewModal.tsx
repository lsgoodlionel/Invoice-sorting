import { Modal } from '@mantine/core';
import type { Attachment } from '../../../api/types';
import { AttachmentPreview } from '../../AttachmentPreview';

const PREVIEW_HEIGHT = 640;

export function PreviewModal({ attachment, onClose }: { attachment: Attachment | null; onClose: () => void }) {
  return (
    <Modal opened={attachment !== null} onClose={onClose} title={attachment?.original_name} size="xl">
      {attachment && <AttachmentPreview attachment={attachment} height={PREVIEW_HEIGHT} />}
    </Modal>
  );
}
