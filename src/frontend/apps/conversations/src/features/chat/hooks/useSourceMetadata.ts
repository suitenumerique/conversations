import { useCallback, useRef, useState } from 'react';

interface SourceMetadata {
  title: string | null;
  favicon: string | null;
  loading: boolean;
  error: boolean;
}

// Cache global pour éviter de refetch les mêmes URLs
const metadataCache = new Map<string, SourceMetadata>();
const fetchingUrls = new Set<string>();

export const useSourceMetadataCache = () => {
  const [, forceUpdate] = useState({});
  const updateCountRef = useRef(0);

  const triggerUpdate = useCallback(() => {
    updateCountRef.current++;
    if (updateCountRef.current % 5 === 0) {
      forceUpdate({});
    }
  }, []);

  const prefetchMetadata = useCallback(
    async (url: string) => {
      if (metadataCache.has(url) || fetchingUrls.has(url)) {
        return;
      }

      fetchingUrls.add(url);

      metadataCache.set(url, {
        title: null,
        favicon: null,
        loading: true,
        error: false,
      });
      triggerUpdate();

      try {
        if (!url.startsWith('http')) {
          metadataCache.set(url, {
            title: url,
            favicon: '📄',
            loading: false,
            error: false,
          });
          fetchingUrls.delete(url);
          triggerUpdate();
          return;
        }

        const parser = new DOMParser();

        let response;
        try {
          response = await fetch(url, {
            mode: 'cors',
            headers: {
              'User-Agent': 'Mozilla/5.0 (compatible; ChatBot/1.0)',
            },
          });
        } catch {
          // Si CORS échoue, utiliser juste le hostname
          metadataCache.set(url, {
            title: new URL(url).hostname,
            favicon: null,
            loading: false,
            error: false,
          });
          fetchingUrls.delete(url);
          triggerUpdate();
          return;
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const html = await response.text();
        const doc = parser.parseFromString(html, 'text/html');

        // Récupérer le titre
        const pageTitle =
          doc.querySelector('title')?.textContent || new URL(url).hostname;

        // Récupérer le favicon
        let faviconUrl =
          doc.querySelector('link[rel="icon"]')?.getAttribute('href') ||
          doc.querySelector('link[rel="shortcut icon"]')?.getAttribute('href');

        if (!faviconUrl) {
          const urlObj = new URL(url);
          faviconUrl = `${urlObj.origin}/favicon.ico`;
        }

        // Convertir les URLs relatives en absolues
        if (faviconUrl && !faviconUrl.startsWith('http')) {
          const urlObj = new URL(url);
          faviconUrl = new URL(faviconUrl, urlObj.origin).href;
        }

        metadataCache.set(url, {
          title: pageTitle,
          favicon: faviconUrl || null,
          loading: false,
          error: false,
        });
        fetchingUrls.delete(url);
        triggerUpdate();
      } catch (err) {
        console.log('Error fetching metadata for:', url, err);
        metadataCache.set(url, {
          title: new URL(url).hostname,
          favicon: null,
          loading: false,
          error: true,
        });
        fetchingUrls.delete(url);
        triggerUpdate();
      }
    },
    [triggerUpdate],
  );

  const getMetadata = useCallback((url: string): SourceMetadata | undefined => {
    return metadataCache.get(url);
  }, []);

  return { prefetchMetadata, getMetadata };
};
