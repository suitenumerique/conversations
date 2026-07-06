import { Message } from '@ai-sdk/ui-utils';

type Co2Annotation = { co2_impact?: number };

export const getMessageCo2Impact = (message: Message): number | undefined => {
  const annotations = (message as Message & { annotations?: Co2Annotation[] })
    .annotations;
  const impact = annotations
    ?.map((annotation) => annotation as Co2Annotation)
    .find(
      (annotation) => typeof annotation.co2_impact === 'number',
    )?.co2_impact;

  if (impact !== undefined && impact > 0) {
    return impact;
  }

  return undefined;
};
