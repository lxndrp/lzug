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

export type DemoScenarioOverview = {
  created_at: string;
  current_role: DemoRole;
  demo_matrix_version: string;
  expires_at: string;
  location_contract: string;
  mode: 'demo';
  notices: string[];
  prepared_plan_change: {
    assignment_id: number;
    day_id: number;
    reason: string;
    replacement_member_id: number;
    round_id: number;
    source_location_id: number;
    target_location_id: number;
  };
  remaining_seconds: number;
  roles: DemoScenarioRole[];
  scenarios: DemoScenario[];
};
