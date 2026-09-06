import { Directive, ElementRef, Input } from '@angular/core';
import type { IconNode } from 'lucide';

@Directive({ selector: '[cIcon]' })
export class AppIconDirective {
  private readonly element: SVGElement;

  constructor(element: ElementRef<SVGElement>) {
    this.element = element.nativeElement;
  }

  @Input() set cIcon(icon: IconNode | null | undefined) {
    this.element.replaceChildren();
    this.element.setAttribute('viewBox', '0 0 24 24');
    this.element.setAttribute('fill', 'none');
    this.element.setAttribute('stroke', 'currentColor');
    this.element.setAttribute('stroke-width', '2');
    this.element.setAttribute('stroke-linecap', 'round');
    this.element.setAttribute('stroke-linejoin', 'round');
    if (!icon) return;

    for (const [tag, attributes] of icon) {
      const child = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [name, value] of Object.entries(attributes)) {
        child.setAttribute(name, String(value));
      }
      this.element.append(child);
    }
  }
}
