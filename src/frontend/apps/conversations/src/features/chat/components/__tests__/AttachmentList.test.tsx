import { render, screen } from '@testing-library/react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { AttachmentList } from '../AttachmentList';

describe('AttachmentList', () => {
  it('renders the filename of a normal attachment without the skipped chip', () => {
    render(
      <AttachmentList
        attachments={[
          { name: 'report.pdf', contentType: 'application/pdf', url: '/u/1' },
        ]}
        isReadOnly={true}
      />,
      { wrapper: AppWrapper },
    );

    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(
      screen.queryByTestId('attachment-skipped-chip'),
    ).not.toBeInTheDocument();
  });

  it('renders the skipped chip with the filename when the attachment was excluded', () => {
    render(
      <AttachmentList
        attachments={[
          {
            name: 'screenshot.png',
            contentType: 'image/png',
            url: '/u/2',
            skipped: { reason: 'model_text_only' },
          },
        ]}
        isReadOnly={true}
      />,
      { wrapper: AppWrapper },
    );

    expect(screen.getByTestId('attachment-skipped-chip')).toBeInTheDocument();
    expect(screen.getByText('screenshot.png')).toBeInTheDocument();
    expect(
      screen.getByText(/Image not used: the current model can't read images./),
    ).toBeInTheDocument();
  });
});
