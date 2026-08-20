import { UIMessage } from 'ai';

import { getMessageCo2Impact } from '../getMessageCo2Impact';

const TEST_CO2_IMPACT_KG = 0.00002191613089507352;

const assistantMessage = (metadata?: unknown): UIMessage => ({
  id: 'trace-1',
  role: 'assistant',
  parts: [{ type: 'text', text: 'Hello' }],
  metadata,
});

describe('getMessageCo2Impact', () => {
  it('returns co2_impact from the message metadata', () => {
    expect(
      getMessageCo2Impact(assistantMessage({ co2_impact: TEST_CO2_IMPACT_KG })),
    ).toBe(TEST_CO2_IMPACT_KG);
  });

  it('returns undefined when metadata is missing', () => {
    expect(getMessageCo2Impact(assistantMessage())).toBeUndefined();
  });

  it('returns undefined when co2_impact is zero', () => {
    expect(
      getMessageCo2Impact(assistantMessage({ co2_impact: 0 })),
    ).toBeUndefined();
  });
});
