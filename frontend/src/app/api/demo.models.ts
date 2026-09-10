import type {
  DemoScenarioOverviewResponse,
  DemoScenarioResponse,
  DemoScenarioRoleResponse,
} from './generated/types.gen';

export type DemoRole = DemoScenarioRoleResponse['name'];

export type DemoScenario = DemoScenarioResponse & {
  id: 'absence' | 'plan-change';
};

export type DemoScenarioOverview = DemoScenarioOverviewResponse & {
  scenarios: DemoScenario[];
};
