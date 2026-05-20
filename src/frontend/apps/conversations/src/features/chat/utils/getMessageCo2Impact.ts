import { Message } from '@ai-sdk/ui-utils';

type Co2Annotation = {
  co2_impact?: number;
};

/**
 * Returns the carbon footprint (kg CO₂eq) attached to an assistant message.
 * Populated by the backend from Albert API usage (`impacts.kgCO2eq`).
 */
export const getMessageCo2Impact = (message: Message): number | undefined => {
  const annotations = (
    message as Message & { annotations?: Co2Annotation[] }
  ).annotations;

  if (!annotations?.length) {
    return undefined;
  }

  for (const annotation of annotations) {
    if (
      typeof annotation !== 'object' ||
      annotation === null ||
      !('co2_impact' in annotation)
    ) {
      continue;
    }
    const value = (annotation as Co2Annotation).co2_impact;
    if (typeof value === 'number' && value > 0) {
      return value;
    }
  }

  return undefined;
};
