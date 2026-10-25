export type DemoRole = 'chair' | 'examiner' | 'replacement';

export type DemoScenario = {
  completed_steps: number;
  id: 'absence' | 'plan-change';
  next_action: string;
  next_role: DemoRole;
  path: string;
  status: 'ready' | 'in_progress' | 'complete';
  title: string;
  total_steps: number;
};

export type DemoScenarioRole = {
  display_name: string;
  name: DemoRole;
  task: string;
};
