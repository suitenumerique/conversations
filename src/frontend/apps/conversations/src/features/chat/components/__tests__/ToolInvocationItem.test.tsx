import { render, screen } from '@testing-library/react';

import { ToolInvocationItem } from '../ToolInvocationItem';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('ToolInvocationItem', () => {
  describe('conversation_resume', () => {
    it('shows the resuming loader when state is call', () => {
      render(
        <ToolInvocationItem
          toolInvocation={{
            toolCallId: 'test-id',
            toolName: 'conversation_resume',
            state: 'call',
            args: {},
          }}
        />,
      );

      expect(
        screen.getByText('Picking up where you left off'),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'Bringing this conversation and its documents back. This may take a moment longer than usual.',
        ),
      ).toBeInTheDocument();
    });

    it('renders nothing when state is result', () => {
      const { container } = render(
        <ToolInvocationItem
          toolInvocation={{
            toolCallId: 'test-id',
            toolName: 'conversation_resume',
            state: 'result',
            args: {},
            result: { state: 'done' },
          }}
        />,
      );

      expect(container).toBeEmptyDOMElement();
    });
  });
});
