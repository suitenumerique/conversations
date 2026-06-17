import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { ProjectImagesSkippedBanner } from '../ProjectImagesSkippedBanner';

describe('ProjectImagesSkippedBanner', () => {
  it('renders the warning copy and calls onDismiss when the user clicks Dismiss', async () => {
    const user = userEvent.setup();
    const onDismiss = jest.fn();

    render(<ProjectImagesSkippedBanner onDismiss={onDismiss} />, {
      wrapper: AppWrapper,
    });

    expect(
      screen.getByTestId('project-images-skipped-banner'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/project images aren't being used/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
