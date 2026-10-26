import {
  isAttendanceStatus,
  isExecutionStatusSummaryState,
  reopeningScopeFromToken,
} from './exam-day.models';

describe('exam-day boundary guards', () => {
  it('accepts only known attendance and summary states', () => {
    expect(isAttendanceStatus('late')).toBe(true);
    expect(isAttendanceStatus('unknown')).toBe(false);
    expect(isAttendanceStatus(null)).toBe(false);
    expect(isExecutionStatusSummaryState('needs_follow_up')).toBe(true);
    expect(isExecutionStatusSummaryState('future_state')).toBe(false);
  });

  it('parses only supported reopening scope tokens with positive safe integer IDs', () => {
    expect(reopeningScopeFromToken('exam_protocol:41')).toEqual({
      kind: 'exam_protocol',
      entityId: 41,
    });
    for (const token of [
      'unknown:41',
      'exam_protocol:0',
      'exam_protocol:-1',
      'exam_protocol:1.5',
      'exam_protocol:1e2',
      'exam_protocol:9007199254740992',
      'exam_protocol:41:extra',
      ':41',
      'exam_protocol:',
    ]) {
      expect(reopeningScopeFromToken(token)).toBeNull();
    }
    expect(reopeningScopeFromToken(null)).toBeNull();
  });
});
