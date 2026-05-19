import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import AttachedDocumentIcon from '@/assets/icons/uikit-custom/attached-document.svg?react';
import { Box, Icon, StyledLink, Text } from '@/components';

const sourceContainerCss = `
  display: block;
  border-radius: 4px;
  padding: var(--c--globals--spacings--xs);
  width: 100%;
`;

const webLinkCss = `
  ${sourceContainerCss}
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
`;

const styles: Record<string, React.CSSProperties> = {
  webTitle: {
    color: 'var(--c--contextuals--content--semantic--neutral--secondary)',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginBottom: '4px',
  },
  documentTitle: {
    color: 'var(--c--contextuals--content--semantic--brand--tertiary)',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginBottom: '4px',
  },
  documentFileName: {
    color: 'var(--c--contextuals--content--semantic--neutral--primary)',
    fontWeight: '500',
    overflowWrap: 'anywhere',
    wordBreak: 'break-word',
  },
};

const isWebSourceUrl = (url: string) => /^https?:\/\//i.test(url);

const getDocumentFileName = (url: string) =>
  url.endsWith('.md') ? url.slice(0, -3) : url;

const webDescriptionStyle: React.CSSProperties = {
  color: 'var(--c--contextuals--content--semantic--neutral--primary)',
  fontWeight: '500',
};

const documentFileNameCss = `
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
  width: 100%;
  min-width: 0;
`;

const documentSourceCss = `
  font-size: 14px;
  min-width: 0;
  ${sourceContainerCss}
`;

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
    if (!isWebSourceUrl(url)) {
      return;
    }
    if (metadata && !metadata.loading) {
      return;
    }
    const fetchMetadata = async () => {
      try {
        setLoading(true);
        setError(false);

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

  const renderDocumentType = () => (
    <>
      <AttachedDocumentIcon
        width={13}
        height={16}
        aria-hidden
        style={{
          display: 'inline-block',
          flexShrink: 0,
          marginLeft: 'var(--c--globals--spacings--xxxs)',
          marginRight: 'var(--c--globals--spacings--xxxs)',
          verticalAlign: 'middle',
          color: 'var(--c--contextuals--content--semantic--brand--tertiary)',
        }}
      />
      {t('Attached document')}
    </>
  );

  const renderWebType = () => {
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

    return (
      <Box
        $margin={{ horizontal: 'xxxs' }}
        $align="center"
        $css="display: inline-flex; flex-shrink: 0; line-height: 0;"
      >
        <img
          src={favicon}
          alt="favicon"
          width={16}
          height={16}
          onError={() => setFavicon(null)}
        />
      </Box>
    );
  };

  if (!isWebSourceUrl(url)) {
    const fileName = getDocumentFileName(url);

    return (
      <Box
        $direction="row"
        $gap="4px"
        $align="flex-start"
        $css="min-width: 0; width: 100%;"
      >
        <Box
          $direction="column"
          $align="flex-start"
          $css={documentSourceCss}
          $width="100%"
        >
          <Box
            $padding={{ right: '4px' }}
            $align="center"
            $direction="row"
            $width="100%"
            $css="min-width: 0;"
            style={styles.documentTitle}
          >
            {index} · {renderDocumentType()}
          </Box>
          <Text
            title={fileName}
            style={styles.documentFileName}
            $css={documentFileNameCss}
          >
            {fileName}
          </Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box $direction="row" $gap="4px" $align="center">
      <Box
        $direction="row"
        $align="center"
        $css="font-size: 14px;"
        $width="100%"
      >
        <StyledLink
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          $css={webLinkCss}
        >
          <Box
            $padding={{ right: '4px' }}
            $align="center"
            $direction="row"
            style={styles.webTitle}
          >
            {index} · {renderWebType()}{' '}
            {new URL(url).hostname ? `| ${new URL(url).hostname}` : ''}
          </Box>
          <Text style={webDescriptionStyle}>{title}</Text>
        </StyledLink>
      </Box>
    </Box>
  );
};
