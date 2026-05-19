import Image from 'next/image';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, StyledLink, Text } from '@/components';

const styles: Record<string, React.CSSProperties> = {
  title: {
    color: 'var(--c--contextuals--content--semantic--neutral--secondary)',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginBottom: '4px',
  },
  description: {
    color: 'var(--c--contextuals--content--semantic--neutral--primary)',
    fontWeight: '500',
  },
};

interface SourceMetadata {
  title: string | null;
  favicon: string | null;
  loading: boolean;
  error: boolean;
}

interface SourceItemProps {
  index: number;
  url: string;
  metadata?: SourceMetadata;
}

export const SourceItem: React.FC<SourceItemProps> = ({
  index,
  url,
  metadata,
}) => {
  const [title, setTitle] = useState<string | null>(metadata?.title || null);
  const [favicon, setFavicon] = useState<string | null>(
    metadata?.favicon || null,
  );
  const [loading, setLoading] = useState(metadata ? metadata.loading : true);
  const [error, setError] = useState(metadata ? metadata.error : false);
  const { t } = useTranslation();

  useEffect(() => {
    if (metadata) {
      setTitle(metadata.title);
      setFavicon(metadata.favicon);
      setLoading(metadata.loading);
      setError(metadata.error);
    }
  }, [metadata]);

  useEffect(() => {
    if (metadata && !metadata.loading) {
      return;
    }
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

    if (url && (!metadata || metadata.loading)) {
      void fetchMetadata();
    }
  }, [url, metadata]);

  // Fallback for favicon if none is found or if there's an error
  const renderType = () => {
    if (loading || error || !favicon) {
      return (
        <>
          <Icon
            iconName="language"
            $theme="neutral"
            $variation="secondary"
            $size="md"
            $margin={{ horizontal: 'xxxs' }}
          />
          {t('Website')}
        </>
      );
    }
    if (favicon === '📄') {
      return <Box>📄</Box>;
    }

    return (
      <Box>
        <Image
          src={favicon}
          alt="favicon"
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
                display: block;
                align-items: center;
                gap: 0.4rem;
                border-radius: 4px;
                padding: var(--c--globals--spacings--xs);
                width: 100%;
                text-decoration: none;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                background-color: transparent;
                transition: background-color 0.3s;
                color: var(--c--contextuals--content--semantic--neutral--tertiary);
                &:hover {
                  background-color: var(--c--contextuals--background--semantic--overlay--primary);
                }
            `}
          >
            <Box
              $padding={{ right: '4px' }}
              $align="center"
              $direction="row"
              style={styles.title}
            >
              {index} · {renderType()}{' '}
              {new URL(url).hostname ? `| ${new URL(url).hostname}` : ''}
            </Box>
            <Text style={styles.description}>{title}</Text>
          </StyledLink>
        ) : (
          <Box>{url}</Box>
        )}
      </Box>
    </Box>
  );
};
