import { render, screen } from '@testing-library/react';

import { InputChatBanner } from '../InputChatBanner';

/**
 * jsdom drops `var()` values, so `toHaveStyle` passes for any expected value
 * and cannot be used for the variant colors. Instead, read the declarations
 * that styled-components injected for the element's own generated classes.
 */
const cssFor = (element: Element): string => {
  // eslint-disable-next-line testing-library/no-node-access
  const css = Array.from(document.querySelectorAll('style'))
    .map((tag) => tag.textContent ?? '')
    .join('');
  return Array.from(element.classList)
    .map((cls) => css.match(new RegExp(`\\.${cls}\\{([^}]*)\\}`))?.[1] ?? '')
    .join(';');
};

describe('<InputChatBanner />', () => {
  it('renders as a status region with the icon and text', () => {
    render(
      <InputChatBanner
        icon={<svg data-testid="banner-icon" />}
        text="Files are being indexed"
      />,
    );

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByTestId('banner-icon')).toBeInTheDocument();
    expect(screen.getByText('Files are being indexed')).toBeInTheDocument();
  });

  it('renders no action by default', () => {
    render(<InputChatBanner icon={<svg />} text="Indexing" />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders the action when provided', () => {
    render(
      <InputChatBanner
        icon={<svg />}
        text="Indexing failed"
        action={<button>Retry</button>}
      />,
    );

    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('uses the warning colors by default', () => {
    render(<InputChatBanner icon={<svg />} text="Heavy load" />);

    const css = cssFor(screen.getByRole('status'));
    expect(css).toContain(
      'background:var(--c--contextuals--background--semantic--warning--tertiary)',
    );
    expect(css).toContain(
      'color:var(--c--contextuals--content--semantic--warning--primary)',
    );
  });

  it('applies the colors of the given variant', () => {
    render(
      <InputChatBanner icon={<svg />} text="Indexing failed" variant="error" />,
    );

    const css = cssFor(screen.getByRole('status'));
    expect(css).toContain(
      'background:var(--c--contextuals--background--semantic--error--tertiary)',
    );
    expect(css).toContain(
      'color:var(--c--contextuals--content--semantic--error--primary)',
    );
  });

  it('cascades the variant color to the icon wrapper and the text', () => {
    render(
      <InputChatBanner
        icon={<svg data-testid="banner-icon" />}
        text="Indexing failed"
        variant="error"
      />,
    );

    const contentColor =
      'color:var(--c--contextuals--content--semantic--error--primary)';
    expect(
      // eslint-disable-next-line testing-library/no-node-access
      cssFor(screen.getByTestId('banner-icon').parentElement as Element),
    ).toContain(contentColor);
    expect(cssFor(screen.getByText('Indexing failed'))).toContain(contentColor);
  });
});
