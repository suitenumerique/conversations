import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';

import { SendButton } from '../SendButton';

describe('SendButton', () => {
  it('should disable the send button when disabled is true', () => {
    render(<SendButton status="ready" disabled={true} />);

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('should enable the send button when disabled is false', () => {
    render(<SendButton status="ready" disabled={false} />);

    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('should keep the stop button enabled while streaming even when disabled is true', () => {
    // A cooldown sets sendDisabled (-> disabled) but must never block Stop.
    render(<SendButton status="streaming" disabled={true} />);

    expect(
      screen.queryByRole('button', { name: 'Send' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
  });

  it('should keep the stop button enabled while submitted even when disabled is true', () => {
    render(<SendButton status="submitted" disabled={true} />);

    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
  });
});
