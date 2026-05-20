import { Message } from '@ai-sdk/ui-utils';

export const getMessageCo2Impact = (message: Message): number | undefined => {
  const annotations = (
    message as Message & { annotations?: { co2_impact?: number }[] }
  ).annotations;
  const impact = annotations?.find(
    (a) => typeof a?.co2_impact === 'number',
  )?.co2_impact;

  return impact && impact > 0 ? impact : undefined;
};
