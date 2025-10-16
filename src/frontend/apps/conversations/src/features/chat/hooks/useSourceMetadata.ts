import { useState } from 'react';

interface SourceMetadata {
  title: string | null;
  favicon: string | null;
  loading: boolean;
  error: boolean;
}

// Cache global pour éviter de refetch les mêmes URLs
const metadataCache = new Map<string, SourceMetadata>();

export const useSourceMetadataCache = () => {
  const [cache, setCache] =
    useState<Map<string, SourceMetadata>>(metadataCache);

  const prefetchMetadata = async (url: string) => {
    // Si déjà en cache, ne rien faire
    if (metadataCache.has(url)) {
      return;
    }

    // Marquer comme en cours de chargement
    metadataCache.set(url, {
      title: null,
      favicon: null,
      loading: true,
      error: false,
    });
    setCache(new Map(metadataCache));

    try {
      if (!url.startsWith('http')) {
        metadataCache.set(url, {
          title: url,
          favicon: '📄',
          loading: false,
          error: false,
        });
        setCache(new Map(metadataCache));
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
        setCache(new Map(metadataCache));
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
      setCache(new Map(metadataCache));
    } catch (err) {
      console.log('Error fetching metadata for:', url, err);
      metadataCache.set(url, {
        title: new URL(url).hostname,
        favicon: null,
        loading: false,
        error: true,
      });
      setCache(new Map(metadataCache));
    }
  };

  const getMetadata = (url: string): SourceMetadata | undefined => {
    return cache.get(url);
  };

  return { prefetchMetadata, getMetadata, cache };
};
