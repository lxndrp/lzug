export type DemoRole = 'chair' | 'examiner' | 'replacement';

export type DemoScenario = {
  id: 'absence' | 'plan-change';
  title: string;
  status: 'ready' | 'in_progress' | 'complete';
  completed_steps: number;
  total_steps: number;
  next_role: DemoRole;
  next_action: string;
  path: string;
};

export type DemoScenarioOverview = {
  mode: 'demo';
  demo_matrix_version: string;
  current_role: DemoRole;
  created_at: string;
  expires_at: string;
  remaining_seconds: number;
  roles: Array<{
    name: DemoRole;
    display_name: string;
    task: string;
  }>;
  scenarios: DemoScenario[];
  prepared_plan_change: {
    round_id: number;
    day_id: number;
    source_location_id: number;
    target_location_id: number;
    assignment_id: number;
    replacement_member_id: number;
    reason: string;
  };
  notices: string[];
  location_contract: string;
};
