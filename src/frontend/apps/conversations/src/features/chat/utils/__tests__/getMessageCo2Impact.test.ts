import { Message } from '@ai-sdk/ui-utils';

import { getMessageCo2Impact } from '../getMessageCo2Impact';

const TEST_CO2_IMPACT_KG = 0.00002191613089507352;

describe('getMessageCo2Impact', () => {
  it('returns co2_impact from annotations', () => {
    const message = {
      id: 'trace-1',
      role: 'assistant',
      content: 'Hello',
      annotations: [{ co2_impact: TEST_CO2_IMPACT_KG }],
    } as Message & { annotations: { co2_impact: number }[] };

    expect(getMessageCo2Impact(message)).toBe(TEST_CO2_IMPACT_KG);
  });

  it('returns undefined when annotations are missing', () => {
    expect(
      getMessageCo2Impact({
        id: '1',
        role: 'assistant',
        content: 'Hello',
      } as Message),
    ).toBeUndefined();
  });

  it('returns undefined when co2_impact is zero', () => {
    expect(
      getMessageCo2Impact({
        id: 'trace-1',
        role: 'assistant',
        content: 'Hello',
        annotations: [{ co2_impact: 0 }],
      } as Message & { annotations: { co2_impact: number }[] }),
    ).toBeUndefined();
  });
});
