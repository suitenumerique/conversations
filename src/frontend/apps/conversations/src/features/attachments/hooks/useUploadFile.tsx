import { useCallback } from 'react';

import { baseApiUrl, fetchAPI, getCSRFToken } from '@/api';
import { useConfig } from '@/core';

import { useCreateConversationAttachment } from '../api';

interface BackendUploadResponse {
  key: string;
}

/**
 * Upload a file, using XHR so we can report on progress through a handler.
 * @param url The pre-signed URL to PUT the file to.
 * @param file The raw file to upload as the request body.
 * @param progressHandler A handler that receives progress updates as a single integer `0 <= x <= 100`.
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

/**
 * Upload a file to the backend (for backend_base64 and backend_temporary_url modes).
 * Uses XHR to track upload progress while respecting the project's API patterns.
 * @param conversationId The ID of the conversation.
 * @param file The file to upload.
 * @param progressHandler A handler that receives progress updates.
 */
export const uploadFileToBackend = (
  conversationId: string,
  file: File,
  progressHandler: (progress: number) => void,
): Promise<BackendUploadResponse> =>
  new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_name', file.name);

    const xhr = new XMLHttpRequest();
    const csrfToken = getCSRFToken();

    xhr.addEventListener('error', reject);
    xhr.addEventListener('abort', reject);

    xhr.addEventListener('readystatechange', () => {
      if (xhr.readyState === 4) {
        if (xhr.status === 201) {
          progressHandler(100);
          try {
            const response = JSON.parse(
              xhr.responseText,
            ) as BackendUploadResponse;
            return resolve(response);
          } catch {
            return reject(new Error('Failed to parse server response'));
          }
        }
        reject(
          new Error(
            `Failed to upload file to backend: ${xhr.status} ${xhr.statusText}`,
          ),
        );
      }
    });

    xhr.upload.addEventListener('progress', (progressEvent) => {
      if (progressEvent.lengthComputable) {
        progressHandler(
          Math.floor((progressEvent.loaded / progressEvent.total) * 100),
        );
      }
    });

    // Use the project's baseApiUrl to construct the endpoint consistently
    const apiUrl = `${baseApiUrl('1.0')}chats/${conversationId}/attachments/backend-upload/`;
    xhr.open('POST', apiUrl);

    // Add authentication headers following the project's pattern
    xhr.withCredentials = true;
    if (csrfToken) {
      xhr.setRequestHeader('X-CSRFToken', csrfToken);
    }

    xhr.send(formData);
  });

export const useUploadFile = (conversationId: string) => {
  const {
    mutateAsync: createConversationAttachment,
    isError: isErrorAttachment,
    error: errorAttachment,
  } = useCreateConversationAttachment();

  const { data: conf } = useConfig();

  const uploadFile = useCallback(
    async (file: File, progressHandler?: (progress: number) => void) => {
      // Backend mode backend_to_s3 file is sent to API backend
      if (conf?.FILE_UPLOAD_MODE === 'backend_to_s3') {
        // Upload file to backend (backend handles S3 storage, MIME detection, and malware scanning)
        const finalAttachment = await uploadFileToBackend(
          conversationId,
          file,
          (progress) => {
            progressHandler?.(progress);
          },
        );

        return `/media-key/${finalAttachment.key}`;
      }

      // Presigned URL mode (default): frontend uploads directly to S3
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
    [createConversationAttachment, conversationId, conf],
  );

  return {
    uploadFile,
    isErrorAttachment,
    errorAttachment,
  };
};
