import { UIMessage } from 'ai';

type InterruptedMetadata = { interrupted?: boolean };

/**
 * True when the backend stored this answer as a checkpoint of a turn that never
 * finished (the connection dropped, or the user pressed stop). The text is
 * whatever had been streamed at that point, so it stops mid-thought.
 */
export const isMessageInterrupted = (message: UIMessage): boolean =>
  (message.metadata as InterruptedMetadata | undefined)?.interrupted === true;
