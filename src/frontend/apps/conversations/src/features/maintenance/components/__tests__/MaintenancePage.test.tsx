import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

import { MaintenancePage } from '../MaintenancePage';

const renderPage = (maintenance: {
  enabled: boolean;
  message?: string | null;
}) => {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MaintenancePage maintenance={maintenance} />
    </QueryClientProvider>,
  );
};

describe('MaintenancePage', () => {
  it('renders the title', () => {
    renderPage({ enabled: true });
    expect(screen.getByText('Service indisponible')).toBeInTheDocument();
  });

  it('renders the static body sentence', () => {
    renderPage({ enabled: true });
    expect(
      screen.getByText(
        /est en cours de maintenance, veuillez nous excuser pour la gêne occasionnée\./,
      ),
    ).toBeInTheDocument();
  });

  it('renders the operator message when provided', () => {
    renderPage({ enabled: true, message: 'Retour prévu à 22h' });
    expect(screen.getByText('Retour prévu à 22h')).toBeInTheDocument();
  });

  it('does not render an extra paragraph when message is blank', () => {
    const { container } = renderPage({ enabled: true, message: '   ' });
    // Counting <p> tags directly: Testing Library has no idiomatic
    // "count-by-tag" query, and queryByText('   ') is unreliable under default
    // whitespace normalization. Only the two static <p> should be present
    // (body sentence + Actions block); a whitespace-only message must not
    // produce a third paragraph.
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    expect(container.querySelectorAll('p')).toHaveLength(2);
  });

  it('renders the Découvrir La Suite link', () => {
    renderPage({ enabled: true });
    const link = screen.getByRole('link', {
      name: /Découvrir La Suite/,
    });
    expect(link).toHaveAttribute('href', 'https://lasuite.numerique.gouv.fr/');
    expect(link).toHaveAttribute('target', '_blank');
  });
});
