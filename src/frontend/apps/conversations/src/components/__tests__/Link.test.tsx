import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StyledLink } from '../Link';

const mockNavigate = vi.hoisted(() => vi.fn());

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => mockNavigate,
}));

describe('StyledLink', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render a link with the correct href', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    expect(link).toHaveAttribute('href', '/test-path');
  });

  it('should navigate on click', async () => {
    const user = userEvent.setup();
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    await user.click(link);

    expect(mockNavigate).toHaveBeenCalledWith('/test-path');
  });

  it('should call onClick prop when clicked', async () => {
    const handleClick = vi.fn();
    const user = userEvent.setup();
    render(
      <StyledLink href="/test-path" onClick={handleClick}>
        Test Link
      </StyledLink>,
    );

    const link = screen.getByRole('link', { name: 'Test Link' });
    await user.click(link);

    expect(handleClick).toHaveBeenCalled();
  });

  it('should allow default behavior when meta key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { metaKey: true });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('should allow default behavior when ctrl key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { ctrlKey: true });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('should allow default behavior when shift key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { shiftKey: true });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('should allow default behavior when alt key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { altKey: true });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('should pass additional props to the anchor element', () => {
    render(
      <StyledLink
        href="/test-path"
        data-testid="custom-link"
        className="custom"
      >
        Test Link
      </StyledLink>,
    );

    const link = screen.getByTestId('custom-link');
    expect(link).toBeInTheDocument();
  });
});
