export type SchedulingStatusGroup = 'draft' | 'coordination' | 'planning' | 'confirmed';

export type SchedulingOverviewItem = {
  id: number;
  name: string;
  status: string;
  statusGroup: SchedulingStatusGroup;
  committeeName: string;
  examHalfYear: { season: 'summer' | 'winter'; year: number };
  calendarWeekFrom: string | null;
  calendarWeekTo: string | null;
};
