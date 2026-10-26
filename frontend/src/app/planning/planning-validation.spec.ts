import { planningValidationViolationsFrom } from './planning-validation';

describe('planning validation boundary guard', () => {
  it('retains complete violations and filters malformed entries', () => {
    const valid = {
      code: 'missing_member',
      message: 'Mitglied fehlt',
      day_id: 2,
      slot_id: null,
      member_id: 7,
    };
    expect(
      planningValidationViolationsFrom({
        violations: [valid, { ...valid, message: 5 }, { ...valid, day_id: '2' }, null],
      }),
    ).toEqual([valid]);
  });

  it.each([null, [], { violations: 'invalid' }, { violations: [{ code: 'bad' }] }])(
    'returns no violations for malformed details: %j',
    (details) => {
      expect(planningValidationViolationsFrom(details)).toEqual([]);
    },
  );
});
