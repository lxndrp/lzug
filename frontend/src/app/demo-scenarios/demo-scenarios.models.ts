/** Roles available in the isolated demonstration workspace. */
export type DemoRole = 'chair' | 'examiner' | 'replacement';

export type DemoScenario = {
  completedSteps: number;
  id: 'absence' | 'plan-change';
  nextAction: string;
  nextRole: DemoRole;
  path: string;
  status: 'ready' | 'in_progress' | 'complete';
  title: string;
  totalSteps: number;
};

export type DemoScenarioRole = {
  displayName: string;
  name: DemoRole;
  task: string;
};

/** Scenario guidance and workspace limits used by the demo UI. */
export type DemoScenarioOverview = {
  createdAt: string;
  currentRole: DemoRole;
  demoMatrixVersion: string;
  expiresAt: string;
  locationContract: string;
  mode: 'demo';
  notices: string[];
  preparedPlanChange: {
    assignmentId: number;
    dayId: number;
    reason: string;
    replacementMemberId: number;
    roundId: number;
    sourceLocationId: number;
    targetLocationId: number;
  };
  remainingSeconds: number;
  roles: DemoScenarioRole[];
  scenarios: DemoScenario[];
};
