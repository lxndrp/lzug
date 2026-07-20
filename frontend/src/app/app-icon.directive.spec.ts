import { ElementRef } from '@angular/core';

import { AppIconDirective } from './app-icon.directive';

describe('AppIconDirective', () => {
  it('applies the icon viewBox together with its path content', () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const directive = new AppIconDirective(
      new ElementRef<HTMLElement>(svg as unknown as HTMLElement),
    );

    directive.cIcon = ['512 512', '<path d="M0 0h512v512H0z"/>'];

    expect(svg.getAttribute('viewBox')).toBe('0 0 512 512');
    expect(svg.querySelector('path')).toBeTruthy();
  });
});
