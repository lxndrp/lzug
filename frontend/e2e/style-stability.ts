import { expect, type Page } from '@playwright/test';

export async function expectFinalStyleState(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.getAnimations().filter((animation) => {
            const endTime = animation.effect?.getComputedTiming().endTime;
            return (
              (animation.playState === 'pending' || animation.playState === 'running') &&
              typeof endTime === 'number' &&
              Number.isFinite(endTime)
            );
          }).length,
      ),
    )
    .toBe(0);
}
