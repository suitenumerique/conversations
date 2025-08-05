import Image from 'next/image';
import React, { useEffect, useState } from 'react';

import { Box, StyledLink } from '@/components';

const styles: Record<string, React.CSSProperties> = {
  title: {
    color: 'var(--c-gray-700, #495057)',
    whiteSpace: 'nowrap',
  },
};

interface SourceItemProps {
  url: string;
}

const SourceItem: React.FC<SourceItemProps> = ({ url }) => {
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
        const response = await fetch(url, { mode: 'cors' });
        const html = await response.text();
        const doc = parser.parseFromString(html, 'text/html');

        // Get the title
        const pageTitle = doc.querySelector('title')?.textContent || url;
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
        console.error('Error fetching metadata:', err);
        setError(true);
        setTitle(url);
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
    <Box $direction="row" $gap="0.25rem" $align="center">
      {renderFavicon()}
      <Box $direction="row" $gap="0.25rem" $align="center">
        {url.startsWith('http') ? (
          <StyledLink
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            $css={`
                text-decoration: none;
                color: var(--c--theme--colors--greyscale-500);
                &:hover {
                  color: var(--c--theme--colors--greyscale-700);
                }
            `}
          >
            {new URL(url).hostname}
          </StyledLink>
        ) : (
          <Box>{url}</Box>
        )}
        <Box $direction="row" $align="center" style={styles.title}>
          {/* Need to better manage the text ellipsis */}
          {title && title.length > 100
            ? `${title.substring(0, 50)}...${title.substring(title.length - 20)}`
            : title}
        </Box>
      </Box>
    </Box>
  );
};

export default SourceItem;
