/** The preset symptom keys (stable API identifiers), grouped the way the picker shows them. */
export const SYMPTOM_GROUPS = [
  { key: 'pain', items: ['cramps', 'headache', 'migraine', 'back_pain', 'breast_tenderness', 'pelvic_pain', 'ovulation_pain'] },
  { key: 'bleeding', items: ['heavy_bleeding', 'spotting', 'discharge'] },
  { key: 'body', items: ['bloating', 'digestion', 'nausea', 'fatigue', 'cravings', 'acne', 'dizziness', 'hot_flashes'] },
  { key: 'mood', items: ['mood_swings', 'irritability', 'anxiety', 'low_mood', 'insomnia', 'poor_focus'] },
] as const;

export const SYMPTOM_KEYS: string[] = SYMPTOM_GROUPS.flatMap((g) => [...g.items]);

/** Shown as one-tap chips before someone has a history of their own. */
export const DEFAULT_QUICK = ['cramps', 'headache', 'fatigue', 'bloating', 'back_pain', 'breast_tenderness', 'mood_swings', 'low_mood'];

export const CUSTOM_MAX_LEN = 40;
export const CUSTOM_MAX_PER_DAY = 10;
