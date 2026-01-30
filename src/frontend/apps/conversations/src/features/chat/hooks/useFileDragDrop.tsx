import { useCallback, useEffect, useState } from 'react';

interface UseFileDragDropOptions {
  /**
   * Whether file upload feature is enabled.
   * When false, drag/drop events are ignored.
   */
  enabled: boolean;

  /**
   * Callback to validate if a file type is accepted.
   * @param file - File to validate
   * @returns true if file should be accepted
   */
  isFileAccepted: (file: File) => boolean;

  /**
   * Callback when files are dropped and validated.
   * Receives only the accepted files.
   */
  onFilesAccepted: (files: File[]) => void;

  /**
   * Callback when some files are rejected due to type.
   * Useful for showing error toasts.
   */
  onFilesRejected?: (fileNames: string[]) => void;
}

interface UseFileDragDropReturn {
  /**
   * Whether a drag operation is currently active over the window.
   * Use this to show a drop overlay.
   */
  isDragActive: boolean;
}

/**
 * Custom hook to handle file drag and drop functionality.
 *
 * Purpose:
 * - Manages window-level drag/drop events for file uploads
 * - Tracks drag state to show/hide drop overlay
 * - Validates files against accepted types
 * - Separates accepted and rejected files
 * - Cleans up event listeners on unmount
 *
 * Why window-level events:
 * - Allows dropping files anywhere on the page
 * - Better UX than requiring precise drop zone targeting
 * - Handles edge cases like dragging over child elements
 *
 * @example
 * const { isDragActive } = useFileDragDrop({
 *   enabled: fileUploadEnabled,
 *   isFileAccepted: (file) => file.type.startsWith('image/'),
 *   onFilesAccepted: (files) => setFiles(files),
 *   onFilesRejected: (names) => showError(`Rejected: ${names.join(', ')}`),
 * });
 */
export const useFileDragDrop = ({
  enabled,
  isFileAccepted,
  onFilesAccepted,
  onFilesRejected,
}: UseFileDragDropOptions): UseFileDragDropReturn => {
  const [isDragActive, setIsDragActive] = useState(false);

  // Process dropped files: separate accepted from rejected
  const processFiles = useCallback(
    (fileList: FileList) => {
      const accepted: File[] = [];
      const rejectedNames: string[] = [];

      Array.from(fileList).forEach((file) => {
        if (isFileAccepted(file)) {
          accepted.push(file);
        } else {
          rejectedNames.push(file.name);
        }
      });

      // Notify about rejected files first (for error toasts)
      if (rejectedNames.length > 0 && onFilesRejected) {
        onFilesRejected(rejectedNames);
      }

      // Then handle accepted files
      if (accepted.length > 0) {
        onFilesAccepted(accepted);
      }
    },
    [isFileAccepted, onFilesAccepted, onFilesRejected],
  );

  // Window-level drag/drop handlers
  useEffect(() => {
    if (!enabled) {
      setIsDragActive(false);
      return;
    }

    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault();
      // Only activate for file drags (not text selections, etc.)
      if (e.dataTransfer?.types.includes('Files')) {
        setIsDragActive(true);
      }
    };

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault();
      // Only deactivate when leaving the window entirely
      // relatedTarget is null when cursor leaves the document
      if (!e.relatedTarget) {
        setIsDragActive(false);
      }
    };

    const handleDragOver = (e: DragEvent) => {
      // Required to allow drop
      e.preventDefault();
    };

    const handleDrop = (e: DragEvent) => {
      e.preventDefault();
      setIsDragActive(false);

      const droppedFiles = e.dataTransfer?.files;
      if (droppedFiles && droppedFiles.length > 0) {
        processFiles(droppedFiles);
      }
    };

    // Attach to window for full-page drag/drop support
    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('drop', handleDrop);

    return () => {
      window.removeEventListener('dragenter', handleDragEnter);
      window.removeEventListener('dragleave', handleDragLeave);
      window.removeEventListener('dragover', handleDragOver);
      window.removeEventListener('drop', handleDrop);
    };
  }, [enabled, processFiles]);

  return {
    isDragActive,
  };
};
