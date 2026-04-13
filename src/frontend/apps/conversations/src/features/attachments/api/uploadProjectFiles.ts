import { baseApiUrl, fetchAPI, getCSRFToken } from '@/api';

import { ConversationAttachment } from '../types';

interface BackendUploadResponse {
  key: string;
}

const createProjectAttachment = async (
  projectId: string,
  file: File,
): Promise<ConversationAttachment> => {
  const response = await fetchAPI(`projects/${projectId}/attachments/`, {
    method: 'POST',
    body: JSON.stringify({
      content_type: file.type,
      file_name: file.name,
      size: file.size,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create attachment for ${file.name}`);
  }

  return response.json() as Promise<ConversationAttachment>;
};

const uploadToPresignedUrl = (url: string, file: File): Promise<void> =>
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
          return resolve();
        }
        reject(new Error(`Failed to upload ${file.name}`));
      }
    });

    xhr.send(file);
  });

const uploadToBackend = (
  projectId: string,
  file: File,
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
          try {
            return resolve(
              JSON.parse(xhr.responseText) as BackendUploadResponse,
            );
          } catch {
            return reject(new Error('Failed to parse server response'));
          }
        }
        reject(new Error(`Failed to upload ${file.name} to backend`));
      }
    });

    const apiUrl = `${baseApiUrl('1.0')}projects/${projectId}/attachments/backend-upload/`;
    xhr.open('POST', apiUrl);
    xhr.withCredentials = true;
    if (csrfToken) {
      xhr.setRequestHeader('X-CSRFToken', csrfToken);
    }
    xhr.send(formData);
  });

/**
 * Upload files to a project. Supports both presigned URL and backend_to_s3 modes.
 */
export const uploadProjectFiles = async (
  projectId: string,
  files: File[],
  uploadMode?: string,
): Promise<void> => {
  for (const file of files) {
    if (uploadMode === 'backend_to_s3') {
      await uploadToBackend(projectId, file);
    } else {
      const attachment = await createProjectAttachment(projectId, file);
      if (!attachment.policy) {
        throw new Error('No policy found');
      }
      await uploadToPresignedUrl(attachment.policy, file);
      const resp = await fetchAPI(
        `projects/${projectId}/attachments/${attachment.id}/upload-ended/`,
        { method: 'POST' },
      );
      if (!resp.ok) {
        throw new Error(`Failed to finalize upload for ${file.name}`);
      }
    }
  }
};
