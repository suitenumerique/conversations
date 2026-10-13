import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import fetchMock from 'fetch-mock';
import React, { useState } from 'react';

import '@/i18n/initI18n';
import { AppWrapper } from '@/tests/utils';

import { InputChat } from '../InputChat';

vi.mock('@/stores', () => ({
  useResponsiveStore: () => ({ isDesktop: true, isMobile: false }),
}));

const mockUseConfig = vi.fn();
const enabledFeatures = new Set<string>();
vi.mock('@/core', () => ({
  useConfig: () => mockUseConfig(),
  useFeatureEnabled: (feature: string) => enabledFeatures.has(feature),
}));

const mockShowToast = vi.fn();
vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

vi.mock('@/features/chat/hooks/useFileDragDrop', () => ({
  useFileDragDrop: () => ({ isDragActive: false }),
}));

vi.mock('@/features/chat/hooks/useFileUrls', () => ({
  useFileUrls: () => new Map(),
}));

vi.mock('../SuggestionCarousel', () => ({
  SuggestionCarousel: () => <div data-testid="suggestion-carousel" />,
}));

vi.mock('../WelcomeMessage', () => ({
  WelcomeMessage: () => <div data-testid="welcome-message" />,
}));

vi.mock('../../assets/files.svg?react', () => ({
  default: () => <svg data-testid="files-icon" />,
}));

// The actions menu is not under test; its ui-kit dropdown needs a provider.
vi.mock('@gouvfr-lasuite/ui-kit', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock('@/features/chat/api/useAssistantHealth', () => ({
  useAssistantHealth: () => ({ data: { banners: [], blocked: false } }),
}));

const TRANSCRIPTIONS_URL =
  'http://test.jest/api/v1.0/voice-prompt/transcriptions/';

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  static supportedTypes = ['audio/webm', 'audio/mp4'];
  static isTypeSupported = (type: string) =>
    FakeMediaRecorder.supportedTypes.includes(type);
  state: 'inactive' | 'recording' = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(
    public stream: MediaStream,
    public options?: MediaRecorderOptions,
  ) {
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = 'recording';
  }

  stop() {
    if (this.state !== 'recording') {
      throw new DOMException('Not recording', 'InvalidStateError');
    }
    this.state = 'inactive';
    this.ondataavailable?.({
      data: new Blob(['audio'], { type: this.mimeType }),
    });
    this.onstop?.();
  }
}

const stopTrack = vi.fn();
const getUserMedia = vi.fn();
const handleSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
const onStop = vi.fn();

const Harness = ({
  initialInput = '',
  conversationId = 'conversation-a',
  status = 'ready',
}: {
  initialInput?: string;
  conversationId?: string;
  status?: string;
}) => {
  const [input, setInput] = useState(initialInput);
  return (
    <InputChat
      messagesLength={0}
      input={input}
      setInput={setInput}
      handleInputChange={(e) => setInput(e.target.value)}
      handleSubmit={handleSubmit}
      status={status}
      onStop={onStop}
      files={null}
      setFiles={vi.fn()}
      conversationId={conversationId}
    />
  );
};

const textbox = () =>
  screen.getByRole('textbox', { name: 'Enter your message or a question' });

const startRecording = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(
    screen.getByRole('button', { name: 'Dictate your message' }),
  );
  await screen.findByRole('button', { name: 'Confirm recording' });
};

describe('InputChat voice prompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.restore();
    FakeMediaRecorder.instances = [];
    enabledFeatures.clear();
    enabledFeatures.add('voice-prompt');
    FakeMediaRecorder.supportedTypes = ['audio/webm', 'audio/mp4'];
    mockUseConfig.mockReturnValue({
      data: {
        FEATURE_FLAGS: {},
        chat_upload_accept: '',
        voice_prompt_enabled: true,
        voice_prompt_max_duration: 300,
      },
    });
    getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('hides the mic when voice prompts are disabled', () => {
    mockUseConfig.mockReturnValue({
      data: {
        FEATURE_FLAGS: {},
        chat_upload_accept: '',
        voice_prompt_enabled: false,
      },
    });
    render(<Harness />, { wrapper: AppWrapper });

    expect(
      screen.queryByRole('button', { name: 'Dictate your message' }),
    ).not.toBeInTheDocument();
  });

  it('hides the mic when the voice-prompt flag is off for the user', () => {
    enabledFeatures.delete('voice-prompt');
    render(<Harness />, { wrapper: AppWrapper });

    expect(
      screen.queryByRole('button', { name: 'Dictate your message' }),
    ).not.toBeInTheDocument();
  });

  it('records at 32 kbps and shows the elapsed time against the cap', async () => {
    const user = userEvent.setup();
    render(<Harness />, { wrapper: AppWrapper });

    await startRecording(user);

    expect(FakeMediaRecorder.instances[0].options).toEqual({
      audioBitsPerSecond: 32000,
      mimeType: 'audio/webm',
    });
    expect(screen.getByText('0:00 / 5:00')).toBeInTheDocument();
  });

  it.each([
    [['audio/webm', 'audio/mp4'], 'audio/webm'],
    [['audio/mp4'], 'audio/mp4'],
    [[], undefined],
  ])(
    'records in a format the backend accepts when the browser supports %j',
    async (supportedTypes, mimeType) => {
      FakeMediaRecorder.supportedTypes = supportedTypes;
      const user = userEvent.setup();
      render(<Harness />, { wrapper: AppWrapper });

      await startRecording(user);

      expect(FakeMediaRecorder.instances[0].options?.mimeType).toBe(mimeType);
    },
  );

  it('appends the transcript to the typed text without sending it', async () => {
    fetchMock.post(TRANSCRIPTIONS_URL, { text: 'bonjour le monde' });
    const user = userEvent.setup();
    render(<Harness />, { wrapper: AppWrapper });

    await user.type(textbox(), 'Compare:');
    await startRecording(user);
    await user.click(screen.getByRole('button', { name: 'Confirm recording' }));

    await waitFor(() =>
      expect(textbox()).toHaveValue('Compare: bonjour le monde'),
    );
    expect(handleSubmit).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
    expect(fetchMock.calls(TRANSCRIPTIONS_URL)).toHaveLength(1);
  });

  it('confirms the recording with Enter without sending', async () => {
    fetchMock.post(TRANSCRIPTIONS_URL, { text: 'world' });
    const user = userEvent.setup();
    render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

    await startRecording(user);
    await user.click(textbox());
    await user.keyboard('{Enter}');

    await waitFor(() => expect(textbox()).toHaveValue('Hello world'));
    expect(fetchMock.calls(TRANSCRIPTIONS_URL)).toHaveLength(1);
    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('appends the transcript to text typed during transcription and blocks sending meanwhile', async () => {
    let release: (value: { text: string }) => void = () => {};
    fetchMock.post(
      TRANSCRIPTIONS_URL,
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

    await startRecording(user);
    expect(
      screen.queryByRole('button', { name: 'Send' }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm recording' }));
    await screen.findByRole('status', { name: 'Transcribing…' });

    expect(
      screen.queryByRole('button', { name: 'Send' }),
    ).not.toBeInTheDocument();
    await user.type(textbox(), ' there{Enter}');
    expect(handleSubmit).not.toHaveBeenCalled();

    act(() => release({ text: 'world' }));

    await waitFor(() => expect(textbox()).toHaveValue('Hello there world'));
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('cancels with Escape without transcribing', async () => {
    const user = userEvent.setup();
    render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

    await startRecording(user);
    await user.keyboard('{Escape}');

    await screen.findByRole('button', { name: 'Dictate your message' });
    expect(fetchMock.called()).toBe(false);
    expect(stopTrack).toHaveBeenCalled();
    expect(textbox()).toHaveValue('Hello');
  });

  it('cancels with the cancel button without transcribing', async () => {
    const user = userEvent.setup();
    render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

    await startRecording(user);
    await user.click(screen.getByRole('button', { name: 'Cancel recording' }));

    await screen.findByRole('button', { name: 'Dictate your message' });
    expect(fetchMock.called()).toBe(false);
    expect(textbox()).toHaveValue('Hello');
  });

  it('auto-stops once at the max duration', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock.post(TRANSCRIPTIONS_URL, { text: 'long dictation' });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<Harness />, { wrapper: AppWrapper });

    await startRecording(user);
    await act(() => vi.advanceTimersByTimeAsync(300_000));
    await waitFor(() => expect(textbox()).toHaveValue('long dictation'));
    await act(() => vi.advanceTimersByTimeAsync(10_000));

    expect(fetchMock.calls(TRANSCRIPTIONS_URL)).toHaveLength(1);
  });

  it.each([
    [413, 'Your recording is too large to be transcribed.'],
    [429, 'You have dictated too many messages. Please try again later.'],
    [
      502,
      'Your recording could not be transcribed. Please try again or type your message.',
    ],
  ])(
    'shows a toast and keeps the input on HTTP %i',
    async (status, message) => {
      fetchMock.post(TRANSCRIPTIONS_URL, status);
      const user = userEvent.setup();
      render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

      await startRecording(user);
      await user.click(
        screen.getByRole('button', { name: 'Confirm recording' }),
      );

      await waitFor(() =>
        expect(mockShowToast).toHaveBeenCalledWith('error', message),
      );
      expect(textbox()).toHaveValue('Hello');
    },
  );

  it('shows a toast when nothing was recognized', async () => {
    fetchMock.post(TRANSCRIPTIONS_URL, { text: '' });
    const user = userEvent.setup();
    render(<Harness initialInput="Hello" />, { wrapper: AppWrapper });

    await startRecording(user);
    await user.click(screen.getByRole('button', { name: 'Confirm recording' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'No speech was recognized in your recording.',
      ),
    );
    expect(textbox()).toHaveValue('Hello');
  });

  it('shows a toast when the microphone is not allowed', async () => {
    getUserMedia.mockRejectedValue(
      new DOMException('denied', 'NotAllowedError'),
    );
    const user = userEvent.setup();
    render(<Harness />, { wrapper: AppWrapper });

    await user.click(
      screen.getByRole('button', { name: 'Dictate your message' }),
    );

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'Microphone access is needed to dictate your message.',
      ),
    );
    expect(
      screen.getByRole('button', { name: 'Dictate your message' }),
    ).toBeInTheDocument();
  });

  it.each([
    ['no microphone', () => new DOMException('none', 'NotFoundError')],
    ['a busy microphone', () => new DOMException('busy', 'NotReadableError')],
    ['a page not served over HTTPS', () => new TypeError('no mediaDevices')],
  ])(
    'tells the user the microphone is unavailable on %s',
    async (_case, error) => {
      getUserMedia.mockRejectedValue(error());
      const user = userEvent.setup();
      render(<Harness />, { wrapper: AppWrapper });

      await user.click(
        screen.getByRole('button', { name: 'Dictate your message' }),
      );

      await waitFor(() =>
        expect(mockShowToast).toHaveBeenCalledWith(
          'error',
          'Your microphone could not be used. Check that it is connected and not used by another application.',
        ),
      );
    },
  );

  it('releases the microphone when the recorder cannot start', async () => {
    vi.stubGlobal(
      'MediaRecorder',
      class extends FakeMediaRecorder {
        start() {
          throw new DOMException('unsupported', 'NotSupportedError');
        }
      },
    );
    const user = userEvent.setup();
    render(<Harness />, { wrapper: AppWrapper });

    await user.click(
      screen.getByRole('button', { name: 'Dictate your message' }),
    );

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'error',
        'Your microphone could not be used. Check that it is connected and not used by another application.',
      ),
    );
    expect(stopTrack).toHaveBeenCalled();
    await user.click(
      screen.getByRole('button', { name: 'Dictate your message' }),
    );
    expect(getUserMedia).toHaveBeenCalledTimes(2);
  });

  it('discards a recording when the user moves to another conversation', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Harness />, { wrapper: AppWrapper });

    await startRecording(user);
    rerender(<Harness conversationId="conversation-b" />);

    await screen.findByRole('button', { name: 'Dictate your message' });
    expect(stopTrack).toHaveBeenCalled();
    expect(fetchMock.called()).toBe(false);
  });

  it('drops a transcription that returns after the user moved to another conversation', async () => {
    let release: (value: { text: string }) => void = () => {};
    fetchMock.post(
      TRANSCRIPTIONS_URL,
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const user = userEvent.setup();
    const { rerender } = render(<Harness initialInput="Hello" />, {
      wrapper: AppWrapper,
    });

    await startRecording(user);
    await user.click(screen.getByRole('button', { name: 'Confirm recording' }));
    await screen.findByRole('status', { name: 'Transcribing…' });
    rerender(<Harness initialInput="Hello" conversationId="conversation-b" />);

    await screen.findByRole('button', { name: 'Dictate your message' });
    await act(async () => {
      release({ text: 'from conversation A' });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(textbox()).toHaveValue('Hello');
    expect(mockShowToast).not.toHaveBeenCalled();
  });

  it('keeps the stop button while a reply streams during a recording', async () => {
    const user = userEvent.setup();
    render(<Harness status="streaming" />, { wrapper: AppWrapper });

    await startRecording(user);
    await user.click(screen.getByRole('button', { name: 'Stop' }));

    expect(onStop).toHaveBeenCalled();
    expect(
      screen.getByRole('button', { name: 'Confirm recording' }),
    ).toBeInTheDocument();
  });

  it('opens the microphone once when the mic is clicked twice', async () => {
    let grant: (stream: unknown) => void = () => {};
    getUserMedia.mockReturnValue(
      new Promise((resolve) => {
        grant = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<Harness />, { wrapper: AppWrapper });

    const mic = screen.getByRole('button', { name: 'Dictate your message' });
    await user.click(mic);
    await user.click(mic);
    act(() => grant({ getTracks: () => [{ stop: stopTrack }] }));

    await screen.findByRole('button', { name: 'Confirm recording' });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });

  it('releases a microphone granted after unmount', async () => {
    let grant: (stream: unknown) => void = () => {};
    getUserMedia.mockReturnValue(
      new Promise((resolve) => {
        grant = resolve;
      }),
    );
    const user = userEvent.setup();
    const { unmount } = render(<Harness />, { wrapper: AppWrapper });

    await user.click(
      screen.getByRole('button', { name: 'Dictate your message' }),
    );
    unmount();
    await act(async () => {
      grant({ getTracks: () => [{ stop: stopTrack }] });
      await Promise.resolve();
    });

    expect(stopTrack).toHaveBeenCalled();
    expect(FakeMediaRecorder.instances).toHaveLength(0);
  });

  it('releases the microphone on unmount', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness />, { wrapper: AppWrapper });

    await startRecording(user);
    unmount();

    expect(stopTrack).toHaveBeenCalled();
    expect(fetchMock.called()).toBe(false);
  });
});
