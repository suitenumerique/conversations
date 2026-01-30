import { useEffect, useRef, useState } from 'react';

/**
 * Manages object URLs for file previews with proper memory cleanup.
 *
 * - Reuses URLs for unchanged files across re-renders
 * - Revokes URLs when files are removed
 * - Cleans up all URLs on unmount
 *
 * @param files - FileList from input or drag/drop, or null
 * @returns Map of file keys (`${name}-${size}-${lastModified}`) to object URLs
 */
export const useFileUrls = (files: FileList | null) => {
  const [urlMap, setUrlMap] = useState<Map<string, string>>(new Map());
  const urlMapRef = useRef<Map<string, string>>(new Map());

  // Keep ref in sync with latest state
  useEffect(() => {
    urlMapRef.current = urlMap;
  });

  // Handle URLs when files change
  useEffect(() => {
    const prevMap = urlMapRef.current;

    if (!files) {
      prevMap.forEach((url) => URL.revokeObjectURL(url));
      setUrlMap(new Map());
      return;
    }

    const newMap = new Map<string, string>();
    const currentFileKeys = new Set(
      Array.from(files).map((f) => getFileKey(f)),
    );

    // Reuse or revoke inline
    prevMap.forEach((url, key) => {
      if (currentFileKeys.has(key)) {
        newMap.set(key, url);
      } else {
        URL.revokeObjectURL(url);
      }
    });

    // Create URLs for new files
    Array.from(files).forEach((file) => {
      const key = getFileKey(file);
      if (!newMap.has(key)) {
        newMap.set(key, URL.createObjectURL(file));
      }
    });

    setUrlMap(newMap);
  }, [files]);

  // Unmount-only cleanup
  useEffect(() => {
    return () => {
      urlMapRef.current.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  return urlMap;
};

/**
 * Generates a unique key for a file based on its properties.
 * Used to track file identity across renders.
 */
const getFileKey = (file: File): string => {
  return `${file.name}-${file.size}-${file.lastModified}`;
};
