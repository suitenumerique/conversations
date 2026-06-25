import { Message } from '@ai-sdk/ui-utils';

import {
  isImagesSkippedEvent,
  stampImagesSkippedOnLatestUserMessage,
} from '../useChat';

describe('isImagesSkippedEvent', () => {
  it('accepts a chat_notice event', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'chat_notice',
        reason: 'model_text_only',
      }),
    ).toBe(true);
  });

  it('accepts a last_message_marked event', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'last_message_marked',
        reason: 'model_text_only',
      }),
    ).toBe(true);
  });

  it('rejects events of other types', () => {
    expect(isImagesSkippedEvent({ type: 'context_trimmed' })).toBe(false);
  });

  it('rejects events with unknown kind', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        kind: 'something-else',
        reason: 'model_text_only',
      }),
    ).toBe(false);
  });

  it('rejects events with missing kind', () => {
    expect(
      isImagesSkippedEvent({
        type: 'images_skipped',
        reason: 'model_text_only',
      }),
    ).toBe(false);
  });

  it('rejects non-objects', () => {
    expect(isImagesSkippedEvent(null)).toBe(false);
    expect(isImagesSkippedEvent('images_skipped')).toBe(false);
    expect(isImagesSkippedEvent(undefined)).toBe(false);
  });
});

const makeUserMessage = (
  id: string,
  attachments: Message['experimental_attachments'],
): Message => ({
  id,
  role: 'user',
  content: 'hi',
  experimental_attachments: attachments,
});

const makeAssistantMessage = (id: string): Message => ({
  id,
  role: 'assistant',
  content: 'hello',
});

describe('stampImagesSkippedOnLatestUserMessage', () => {
  it('stamps skipped on every image attachment of the latest user message', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'a.png', contentType: 'image/png', url: 'http://a' },
        { name: 'b.pdf', contentType: 'application/pdf', url: 'http://b' },
      ]),
      makeAssistantMessage('2'),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result).not.toBe(messages);
    const updatedAttachments = result[0].experimental_attachments!;
    expect(updatedAttachments[0]).toMatchObject({
      name: 'a.png',
      skipped: { reason: 'model_text_only' },
    });
    expect(updatedAttachments[1]).toMatchObject({ name: 'b.pdf' });
    expect((updatedAttachments[1] as { skipped?: unknown }).skipped).toBe(
      undefined,
    );
  });

  it('returns the same reference when no images are present', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'doc.pdf', contentType: 'application/pdf', url: 'http://x' },
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when images are already stamped', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        {
          name: 'a.png',
          contentType: 'image/png',
          url: 'http://a',
          // already stamped by an earlier event
          ...({ skipped: { reason: 'model_text_only' } } as Record<
            string,
            unknown
          >),
        },
      ]),
    ];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('returns the same reference when there is no user message', () => {
    const messages: Message[] = [makeAssistantMessage('1')];

    expect(stampImagesSkippedOnLatestUserMessage(messages)).toBe(messages);
  });

  it('only touches the latest user message', () => {
    const messages: Message[] = [
      makeUserMessage('1', [
        { name: 'old.png', contentType: 'image/png', url: 'http://old' },
      ]),
      makeAssistantMessage('2'),
      makeUserMessage('3', [
        { name: 'new.png', contentType: 'image/png', url: 'http://new' },
      ]),
    ];

    const result = stampImagesSkippedOnLatestUserMessage(messages);

    expect(result[0]).toBe(messages[0]); // untouched
    expect(result[2]).not.toBe(messages[2]);
    expect(
      (result[2].experimental_attachments![0] as { skipped?: unknown }).skipped,
    ).toEqual({ reason: 'model_text_only' });
  });
});
