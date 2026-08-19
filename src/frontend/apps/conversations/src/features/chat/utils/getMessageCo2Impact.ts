import { UIMessage } from 'ai';

type Co2Metadata = { co2_impact?: number };

export const getMessageCo2Impact = (message: UIMessage): number | undefined => {
  const impact = (message.metadata as Co2Metadata | undefined)?.co2_impact;

  if (typeof impact === 'number' && impact > 0) {
    return impact;
  }

  return undefined;
};
