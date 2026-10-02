/** A one-shot UI effect delivered to the currently active locations view. */
export type VenueViewEffectCommand =
  { type: 'reset-draft' } | { type: 'finish-editing'; id: number };
export type VenueViewEffect = VenueViewEffectCommand & { version: number };
