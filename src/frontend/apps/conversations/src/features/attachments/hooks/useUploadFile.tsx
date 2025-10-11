import { useCallback } from 'react';

import { fetchAPI } from '@/api';

import { useCreateConversationAttachment } from '../api';

/**
 * Upload a file, using XHR so we can report on progress through a handler.
 * @param url The pre-signed URL to PUT the file to.
 * @param file The raw file to upload as the request body.
 * @param progressHandler A handler that receives progress updates as a single integer `0 <= x <= 100`.
 */
export const uploadFileToServer = (
  url: string,
  file: File,
  progressHandler: (progress: number) => void,
) =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.setRequestHeader('X-amz-acl', 'private');
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.addEventListener('error', reject);
    xhr.addEventListener('abort', reject);

    xhr.addEventListener('readystatechange', () => {
      if (xhr.readyState === 4) {
        if (xhr.status === 200) {
          // Make sure to always set the progress to 100% when the upload is done.
          // Because 'progress' event listener is not called when the file size is 0.
          progressHandler(100);
          return resolve(true);
        }
        reject(new Error(`Failed to perform the upload on ${url}.`));
      }
    });

    xhr.upload.addEventListener('progress', (progressEvent) => {
      if (progressEvent.lengthComputable) {
        progressHandler(
          Math.floor((progressEvent.loaded / progressEvent.total) * 100),
        );
      }
    });

    xhr.send(file);
  });

export const useUploadFile = (conversationId: string) => {
  const {
    mutateAsync: createConversationAttachment,
    isError: isErrorAttachment,
    error: errorAttachment,
  } = useCreateConversationAttachment();

  const uploadFile = useCallback(
    async (file: File, progressHandler?: (progress: number) => void) => {
      const attachment = await createConversationAttachment({
        conversationId,
        content_type: file.type,
        file_name: file.name,
        size: file.size,
      });

      if (!attachment.policy) {
        throw new Error('No policy found');
      }

      await uploadFileToServer(attachment.policy, file, (progress) => {
        progressHandler?.(progress);
      });

      const finalizeResp = await fetchAPI(
        `chats/${conversationId}/attachments/${attachment.id}/upload-ended/`,
        {
          method: 'POST',
        },
      );
      if (!finalizeResp.ok) {
        throw new Error('Failed to finalize the upload');
      }

      return `/media-key/${attachment.key}`;
    },
    [createConversationAttachment, conversationId],
  );

  return {
    uploadFile,
    isErrorAttachment,
    errorAttachment,
  };
};
