import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { confirmedPlan, examProtocolView } from './quality-support';

test('keeps the exam-protocol editor keyboard-accessible @a11y', async ({ page }) => {
  const plan = confirmedPlan(1, 'Prüfungsausschuss Protokoll', 'Prüfling', 'Protokoll', 'regular');
  const day = plan.days[0];
  day.slots[0].actual_started_at = '2026-11-16T08:31:00+01:00';
  day.slots[0].execution_status = 'running';
  day.status_summary = {
    open: 0,
    running: 1,
    completed: 0,
    cancelled: 0,
    needs_follow_up: 0,
  };

  await page.route('**/api/confirmed-plan-days/1', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        plan: {
          id: plan.id,
          name: plan.name,
          committee: plan.committee,
          exam_half_year: plan.exam_half_year,
        },
        day,
        _links: {},
      }),
    }),
  );
  await page.route('**/api/confirmed-plan-days/1/slots/1/protocol', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(examProtocolView()) }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/confirmed-plans/1/days/1');

  const protocol = page.locator('app-exam-protocol');
  await expect(protocol.getByRole('heading', { name: 'Gestarteter Slot 1' })).toBeVisible();
  await expect(protocol.getByRole('radio', { name: 'Ohne besondere Vorkommnisse' })).toBeVisible();
  await protocol.getByRole('radio', { name: 'Mit besonderen Vorkommnissen' }).focus();
  await expect(protocol.getByRole('radio', { name: 'Mit besonderen Vorkommnissen' })).toBeFocused();
  expect(
    (await new AxeBuilder({ page }).include('app-exam-protocol').analyze()).violations,
  ).toEqual([]);
});
