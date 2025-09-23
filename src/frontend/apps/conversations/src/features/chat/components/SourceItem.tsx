import Image from 'next/image';
import React, { useEffect, useState } from 'react';

import { Box, StyledLink } from '@/components';

const styles: Record<string, React.CSSProperties> = {
  title: {
    color: '#222631',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    display: 'block',
  },
};

interface SourceItemProps {
  url: string;
}

export const SourceItem: React.FC<SourceItemProps> = ({ url }) => {
  const [title, setTitle] = useState<string | null>(null);
  const [favicon, setFavicon] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const fetchMetadata = async () => {
      try {
        setLoading(true);
        setError(false);

        if (!url.startsWith('http')) {
          setLoading(false);
          setFavicon('📄');
          return;
        }

        // We should ideally have a backend endpoint for this
        // but for demonstration, we'll use a simplified approach
        const parser = new DOMParser();

        // Try to fetch with CORS, but handle errors gracefully
        let response;
        try {
          response = await fetch(url, {
            mode: 'cors',
            headers: {
              'User-Agent': 'Mozilla/5.0 (compatible; ChatBot/1.0)',
            },
          });
        } catch {
          console.log('CORS fetch failed, using fallback for:', url);
          // If CORS fails, just use the URL as title
          setTitle(new URL(url).hostname);
          setFavicon(null);
          setLoading(false);
          return;
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const html = await response.text();
        const doc = parser.parseFromString(html, 'text/html');

        // Get the title
        const pageTitle =
          doc.querySelector('title')?.textContent || new URL(url).hostname;
        setTitle(pageTitle);

        // Get the favicon
        // Strategy 1: look for rel="icon" or rel="shortcut icon" link
        let faviconUrl =
          doc.querySelector('link[rel="icon"]')?.getAttribute('href') ||
          doc.querySelector('link[rel="shortcut icon"]')?.getAttribute('href');

        // Strategy 2: use base URL + /favicon.ico
        if (!faviconUrl) {
          const urlObj = new URL(url);
          faviconUrl = `${urlObj.origin}/favicon.ico`;
        }

        // Convert relative URLs to absolute URLs
        if (faviconUrl && !faviconUrl.startsWith('http')) {
          const urlObj = new URL(url);
          faviconUrl = new URL(faviconUrl, urlObj.origin).href;
        }

        setFavicon(faviconUrl || null);
      } catch (err) {
        console.log('Error fetching metadata for:', url, err);
        setError(true);
        setTitle(new URL(url).hostname);
      } finally {
        setLoading(false);
      }
    };

    if (url) {
      void fetchMetadata();
    }
  }, [url]);

  // Fallback for favicon if none is found or if there's an error
  const renderFavicon = () => {
    if (loading || error || !favicon) {
      return <Box>🔗</Box>;
    }
    if (favicon === '📄') {
      return <Box>📄</Box>;
    }

    return (
      <Box>
        <Image
          src={favicon}
          alt="Favicon"
          width={16}
          height={16}
          onError={() => setFavicon(null)}
        />
      </Box>
    );
  };

  return (
    <Box $direction="row" $gap="4px" $align="center">
      <Box
        $direction="row"
        $align="center"
        $css="font-size: 14px;"
        $width="100%"
      >
        {url.startsWith('http') ? (
          <StyledLink
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            $css={`
                display: flex;
                align-items: center;
                gap: 0.4rem;
                border-radius: 4px;
                padding: 4px;
                width: 100%;
                text-decoration: none;
                background-color: transparent;
                transition: background-color 0.3s;
                color: var(--c--theme--colors--greyscale-500);
                &:hover {
                  color: var(--c--theme--colors--greyscale-700);
                  background-color: #EEF1F4;
                }
            `}
          >
            {renderFavicon()}

            {new URL(url).hostname}

            <Box
              $padding={{ right: '4px' }}
              $align="center"
              style={styles.title}
            >
              {title}
            </Box>
          </StyledLink>
        ) : (
          <Box>{url}</Box>
        )}
      </Box>
    </Box>
  );
};
