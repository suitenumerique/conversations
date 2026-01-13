import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StyledLink } from '../Link';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('StyledLink', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render a link with the correct href', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    expect(link).toHaveAttribute('href', '/test-path');
  });

  it('should navigate using router.push on click', async () => {
    const user = userEvent.setup();
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    await user.click(link);

    expect(mockPush).toHaveBeenCalledWith('/test-path');
  });

  it('should call onClick prop when clicked', async () => {
    const handleClick = jest.fn();
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

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('should allow default behavior when ctrl key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { ctrlKey: true });

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('should allow default behavior when shift key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { shiftKey: true });

    expect(mockPush).not.toHaveBeenCalled();
  });

  it('should allow default behavior when alt key is pressed', () => {
    render(<StyledLink href="/test-path">Test Link</StyledLink>);

    const link = screen.getByRole('link', { name: 'Test Link' });
    fireEvent.click(link, { altKey: true });

    expect(mockPush).not.toHaveBeenCalled();
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
