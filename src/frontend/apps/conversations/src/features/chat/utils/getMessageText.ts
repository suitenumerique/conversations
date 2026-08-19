import { UIMessage } from 'ai';

/**
 * The message text, assembled from its text parts.
 *
 * v5 messages carry their text in parts; older stored messages that only had
 * the deprecated `content` field are upconverted to a text part by the backend,
 * so this is the single source of truth on the client.
 */
export const getMessageText = (message: UIMessage): string =>
  message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('');
