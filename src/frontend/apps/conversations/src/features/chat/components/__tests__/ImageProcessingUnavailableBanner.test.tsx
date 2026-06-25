import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { ImageProcessingUnavailableBanner } from '../ImageProcessingUnavailableBanner';

describe('ImageProcessingUnavailableBanner', () => {
  it('renders the headline and calls onDismiss when the user clicks the close button', async () => {
    const user = userEvent.setup();
    const onDismiss = jest.fn();

    render(<ImageProcessingUnavailableBanner onDismiss={onDismiss} />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByTestId('image-processing-unavailable-banner'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/image processing unavailable/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('opens a modal with the explanation when "More info" is clicked', async () => {
    const user = userEvent.setup();

    render(<ImageProcessingUnavailableBanner onDismiss={jest.fn()} />, {
      wrapper: AppWrapper,
    });

    await user.click(screen.getByRole('button', { name: /more info/i }));

    expect(
      await screen.findByText(/image analysis is temporarily unavailable/i),
    ).toBeInTheDocument();
  });
});
