import { ElementRef } from '@angular/core';
import { Plus } from 'lucide';

import { AppIconDirective } from './app-icon.directive';

describe('AppIconDirective', () => {
  it('renders a Lucide icon on its canonical 24 pixel grid', () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const directive = new AppIconDirective(new ElementRef<SVGElement>(svg));

    directive.cIcon = Plus;

    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg.querySelector('path')).toBeTruthy();
  });
});
