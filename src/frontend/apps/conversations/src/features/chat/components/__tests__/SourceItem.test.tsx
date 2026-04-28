import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { SourceItem } from '../SourceItem';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

describe('SourceItem', () => {
  let consoleSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    // Prevent real HTTP calls; override per test as needed
    globalThis.fetch = jest.fn().mockReturnValue(new Promise(() => {}));
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    jest.clearAllMocks();
  });

  describe('non-http URL', () => {
    it('renders as plain text without a link', () => {
      render(<SourceItem url="local-file.txt" />);
      expect(screen.getByText('local-file.txt')).toBeInTheDocument();
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('only shows the URL text, no favicon emoji', () => {
      render(<SourceItem url="local-file.txt" />);
      expect(screen.queryByText('🔗')).not.toBeInTheDocument();
      expect(screen.queryByText('📄')).not.toBeInTheDocument();
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
        <SourceItem url="https://example.com/page" metadata={loadedMetadata} />,
      );
      expect(screen.getByRole('link')).toHaveAttribute(
        'href',
        'https://example.com/page',
      );
    });

    it('opens link in a new tab with security attributes', () => {
      render(
        <SourceItem url="https://example.com" metadata={loadedMetadata} />,
      );
      const link = screen.getByRole('link');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('shows the hostname', () => {
      render(
        <SourceItem url="https://example.com/page" metadata={loadedMetadata} />,
      );
      expect(screen.getByText('example.com')).toBeInTheDocument();
    });

    it('shows the title from metadata', () => {
      render(
        <SourceItem url="https://example.com" metadata={loadedMetadata} />,
      );
      expect(screen.getByText('Example Page')).toBeInTheDocument();
    });
  });

  describe('favicon rendering', () => {
    it('shows 🔗 while loading', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: true, error: false }}
        />,
      );
      expect(screen.getByText('🔗')).toBeInTheDocument();
    });

    it('shows 🔗 on error', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: false, error: true }}
        />,
      );
      expect(screen.getByText('🔗')).toBeInTheDocument();
    });

    it('shows 🔗 when favicon is null', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: null,
            loading: false,
            error: false,
          }}
        />,
      );
      expect(screen.getByText('🔗')).toBeInTheDocument();
    });

    it('shows favicon image when a favicon URL is provided', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: 'https://example.com/favicon.ico',
            loading: false,
            error: false,
          }}
        />,
      );
      expect(screen.getByAltText('Favicon')).toBeInTheDocument();
    });

    it('shows 📄 when favicon is 📄', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{
            title: 'Local',
            favicon: '📄',
            loading: false,
            error: false,
          }}
        />,
      );
      expect(screen.getByText('📄')).toBeInTheDocument();
    });

    it('falls back to 🔗 when favicon image fails to load', () => {
      render(
        <SourceItem
          url="https://example.com"
          metadata={{
            title: 'Example',
            favicon: 'https://example.com/favicon.ico',
            loading: false,
            error: false,
          }}
        />,
      );

      fireEvent.error(screen.getByAltText('Favicon'));

      expect(screen.queryByAltText('Favicon')).not.toBeInTheDocument();
      expect(screen.getByText('🔗')).toBeInTheDocument();
    });
  });

  describe('metadata prop updates', () => {
    it('updates state when metadata changes from loading to loaded', () => {
      const { rerender } = render(
        <SourceItem
          url="https://example.com"
          metadata={{ title: null, favicon: null, loading: true, error: false }}
        />,
      );

      expect(screen.getByText('🔗')).toBeInTheDocument();

      rerender(
        <SourceItem
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
      expect(screen.getByAltText('Favicon')).toBeInTheDocument();
    });
  });

  describe('fetch behavior (no metadata)', () => {
    it('shows 🔗 while fetching', () => {
      render(<SourceItem url="https://example.com" />);
      expect(screen.getByText('🔗')).toBeInTheDocument();
    });

    it('uses hostname as title when CORS fetch fails', async () => {
      (globalThis.fetch as jest.Mock).mockRejectedValue(
        new Error('CORS error'),
      );

      render(<SourceItem url="https://example.com/page" />);

      await waitFor(() =>
        expect(screen.getByRole('link')).toHaveTextContent('example.com'),
      );
    });

    it('parses page title from fetched HTML', async () => {
      (globalThis.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        text: () =>
          Promise.resolve('<html><head><title>My Page</title></head></html>'),
      });

      render(<SourceItem url="https://example.com/page" />);

      expect(await screen.findByText('My Page')).toBeInTheDocument();
    });

    it('uses hostname as title when response is not ok', async () => {
      (globalThis.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 404,
      });

      render(<SourceItem url="https://example.com/page" />);

      await waitFor(() =>
        expect(screen.getByRole('link')).toHaveTextContent('example.com'),
      );
    });

    it('does not fetch when metadata is loaded', () => {
      const fetchSpy = globalThis.fetch as jest.Mock;

      render(
        <SourceItem
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
