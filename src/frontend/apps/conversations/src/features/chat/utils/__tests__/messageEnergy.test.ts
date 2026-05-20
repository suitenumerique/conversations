import { Message } from '@ai-sdk/ui-utils';

import { FAKE_CO2_IMPACT_KG } from '../../fixtures/fakeCo2Message';
import { formatCo2Impact } from '../formatCo2Impact';
import { getMessageCo2Impact } from '../getMessageCo2Impact';

describe('getMessageCo2Impact', () => {
  it('returns co2_impact from annotations', () => {
    const message = {
      id: 'trace-1',
      role: 'assistant',
      content: 'Hello',
      annotations: [{ co2_impact: FAKE_CO2_IMPACT_KG }],
    } as Message & { annotations: { co2_impact: number }[] };

    expect(getMessageCo2Impact(message)).toBe(FAKE_CO2_IMPACT_KG);
  });

  it('returns undefined when annotations are missing', () => {
    const message = {
      id: '1',
      role: 'assistant',
      content: 'Hello',
    } as Message;

    expect(getMessageCo2Impact(message)).toBeUndefined();
  });

  it('returns undefined when co2_impact is zero', () => {
    const message = {
      id: 'trace-1',
      role: 'assistant',
      content: 'Hello',
      annotations: [{ co2_impact: 0 }],
    } as Message & { annotations: { co2_impact: number }[] };

    expect(getMessageCo2Impact(message)).toBeUndefined();
  });
});

describe('formatCo2Impact', () => {
  it('formats milligrams for very small values', () => {
    expect(formatCo2Impact(FAKE_CO2_IMPACT_KG)).toBe('21.92 mg CO₂eq');
  });

  it('formats grams for medium values', () => {
    expect(formatCo2Impact(0.05)).toBe('50 g CO₂eq');
  });

  it('formats kilograms for large values', () => {
    expect(formatCo2Impact(2.5)).toBe('2.5 kg CO₂eq');
  });
});
