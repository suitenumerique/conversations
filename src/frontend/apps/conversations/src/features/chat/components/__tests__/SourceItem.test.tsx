import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Mock, MockInstance } from 'vitest';

import { SourceItem } from '../SourceItem';

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('SourceItem', () => {
  let consoleSpy: MockInstance;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    // Prevent real HTTP calls; override per test as needed
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    vi.clearAllMocks();
  });

  describe('non-http URL', () => {
    it('renders attached document label and filename without a link', () => {
      render(<SourceItem index={1} url="local-file.txt" />);
      expect(screen.getByText(/Attached document/)).toBeInTheDocument();
      expect(screen.getByText('local-file.txt')).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('strips .md suffix from converted document sources', () => {
      render(<SourceItem index={1} url="report.pdf.md" />);
      expect(screen.getByText('report.pdf')).toBeInTheDocument();
    });
  });

  describe('http URL with metadata', () => {
    const loadedMetadata = {
      title: 'Example Page',
      favicon: null,
      loading: false,
      error: false,
    };

    it('renders a link to the URL', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com/page"
          metadata={loadedMetadata}
        />,
      );
      expect(screen.getByRole('link')).toHaveAttribute(
        'href',
        'https://example.com/page',
      );
    });

    it('opens link in a new tab with security attributes', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={loadedMetadata}
        />,
      );
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('shows the hostname', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com/page"
          metadata={loadedMetadata}
        />,
      );
      expect(screen.getByRole('link')).toHaveTextContent(/example\.com/);
    });

    it('shows the title from metadata', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={loadedMetadata}
        />,
      );
      expect(screen.getByText('Example Page')).toBeInTheDocument();
    });
  });

  describe('favicon rendering', () => {
    it('shows Website label while loading', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: true, error: false }}
        />,
      );
      expect(screen.getByRole('link')).toHaveTextContent(/Website/);
    });

    it('shows Website label on error', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: false, error: true }}
        />,
      );
      expect(screen.getByRole('link')).toHaveTextContent(/Website/);
    });

    it('shows Website label when favicon is null', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: null,
            loading: false,
            error: false,
          }}
        />,
      );
      expect(screen.getByRole('link')).toHaveTextContent(/Website/);
    });

    it('shows favicon image when a favicon URL is provided', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: 'https://example.com/favicon.ico',
            loading: false,
            error: false,
          }}
        />,
      );
      expect(screen.getByAltText('favicon')).toBeInTheDocument();
    });

    it('falls back to Website label when favicon image fails to load', () => {
      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: 'https://example.com/favicon.ico',
            loading: false,
            error: false,
          }}
        />,
      );

      fireEvent.error(screen.getByAltText('favicon'));

      expect(screen.queryByAltText('favicon')).not.toBeInTheDocument();
      expect(screen.getByRole('link')).toHaveTextContent(/Website/);
    });
  });

  describe('metadata prop updates', () => {
    it('updates state when metadata changes from loading to loaded', () => {
      const { rerender } = render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: true, error: false }}
        />,
      );

      expect(screen.getByRole('link')).toHaveTextContent(/Website/);

      rerender(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{
            title: 'Loaded Title',
            favicon: 'https://example.com/favicon.ico',
            loading: false,
            error: false,
          }}
        />,
      );

      expect(screen.getByText('Loaded Title')).toBeInTheDocument();
      expect(screen.getByAltText('favicon')).toBeInTheDocument();
    });
  });

  describe('fetch behavior (no metadata)', () => {
    it('shows Website label while fetching', () => {
      render(<SourceItem index={1} url="https://example.com" />);
      expect(screen.getByRole('link')).toHaveTextContent(/Website/);
    });

    it('uses hostname as title when CORS fetch fails', async () => {
      (globalThis.fetch as Mock).mockRejectedValue(new Error('CORS error'));

      render(<SourceItem index={1} url="https://example.com/page" />);

      await waitFor(() =>
        expect(screen.getByRole('link')).toHaveTextContent('example.com'),
      );
    });

    it('parses page title from fetched HTML', async () => {
      (globalThis.fetch as Mock).mockResolvedValue({
        ok: true,
        text: () =>
          Promise.resolve('<html><head><title>My Page</title></head></html>'),
      });

      render(<SourceItem index={1} url="https://example.com/page" />);

      expect(await screen.findByText('My Page')).toBeInTheDocument();
    });

    it('uses hostname as title when response is not ok', async () => {
      (globalThis.fetch as Mock).mockResolvedValue({
        ok: false,
        status: 404,
      });

      render(<SourceItem index={1} url="https://example.com/page" />);

      await waitFor(() =>
        expect(screen.getByRole('link')).toHaveTextContent('example.com'),
      );
    });

    it('does not fetch when metadata is loaded', () => {
      const fetchSpy = globalThis.fetch as Mock;

      render(
        <SourceItem
          index={1}
          url="https://example.com"
          metadata={{
            title: 'Cached',
            favicon: null,
            loading: false,
            error: false,
          }}
        />,
      );

      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });
});
