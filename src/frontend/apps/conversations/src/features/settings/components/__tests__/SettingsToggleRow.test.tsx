import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { SettingsToggleRow } from '../SettingsToggleRow';

const onToggle = vi.fn();

const renderRow = (props: Partial<{ checked: boolean; disabled: boolean }>) => {
  onToggle.mockClear();
  render(
    <SettingsToggleRow
      title="Smart web search"
      description="The assistant decides when to search the web."
      checked={props.checked ?? false}
      disabled={props.disabled ?? false}
      onToggle={onToggle}
      aria-label="Automatic web search"
    />,
    { wrapper: AppWrapper },
  );
};

describe('SettingsToggleRow', () => {
  it('renders the title and description', () => {
    renderRow({});
    expect(screen.getByText('Smart web search')).toBeInTheDocument();
    expect(
      screen.getByText('The assistant decides when to search the web.'),
    ).toBeInTheDocument();
  });

  it('reflects the checked state', () => {
    renderRow({ checked: true });
    expect(screen.getByLabelText('Automatic web search')).toBeChecked();
  });

  it('calls onToggle when clicked', async () => {
    renderRow({});
    await userEvent.click(screen.getByLabelText('Automatic web search'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('is inert while disabled', async () => {
    renderRow({ disabled: true });
    const toggle = screen.getByLabelText('Automatic web search');
    expect(toggle).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(toggle);
    expect(onToggle).not.toHaveBeenCalled();
  });
});
