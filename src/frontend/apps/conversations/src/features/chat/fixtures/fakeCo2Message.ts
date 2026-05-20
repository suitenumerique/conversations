import { Message } from '@ai-sdk/ui-utils';

/** Valeur réelle renvoyée par l’API Albert (kg CO₂eq), pour tests locaux. */
export const FAKE_CO2_IMPACT_KG = 0.00002191613089507352;

export const FAKE_CO2_ANNOTATIONS = [
  { co2_impact: FAKE_CO2_IMPACT_KG },
] as const;

/** Conversation minimale : 1 question utilisateur + 1 réponse avec annotation CO₂. */
export const fakeCo2TestMessages: Message[] = [
  {
    id: 'fake-user-co2',
    role: 'user',
    content: 'Message de test — impact énergétique',
  },
  {
    id: 'trace-fake-co2-test',
    role: 'assistant',
    content:
      'Réponse factice pour tester l’icône feuilles et le tooltip d’empreinte carbone.',
    annotations: [...FAKE_CO2_ANNOTATIONS],
  },
];
