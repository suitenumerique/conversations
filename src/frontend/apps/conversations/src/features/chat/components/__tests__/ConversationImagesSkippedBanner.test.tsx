import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { ConversationImagesSkippedBanner } from '../ConversationImagesSkippedBanner';

describe('ConversationImagesSkippedBanner', () => {
  it('renders the warning copy and calls onDismiss when the user clicks Dismiss', async () => {
    const user = userEvent.setup();
    const onDismiss = jest.fn();

    render(
      <ConversationImagesSkippedBanner
        names={['sample.png']}
        onDismiss={onDismiss}
      />,
      { wrapper: AppWrapper },
    );

    expect(
      screen.getByTestId('conversation-images-skipped-banner'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/images in this conversation aren't being used/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('opens a modal listing the skipped image filenames', async () => {
    const user = userEvent.setup();

    render(
      <ConversationImagesSkippedBanner
        names={['sample.png', 'scan.jpg']}
        onDismiss={jest.fn()}
      />,
      { wrapper: AppWrapper },
    );

    await user.click(screen.getByRole('button', { name: /see details/i }));

    const details = await screen.findByTestId(
      'conversation-images-skipped-details',
    );
    expect(details).toHaveTextContent('sample.png');
    expect(details).toHaveTextContent('scan.jpg');
  });
});
