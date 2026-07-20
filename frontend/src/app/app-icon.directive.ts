import { Directive, ElementRef, Input } from '@angular/core';

@Directive({ selector: '[cIcon]' })
export class AppIconDirective {
  private readonly element: HTMLElement;

  constructor(element: ElementRef<HTMLElement>) {
    this.element = element.nativeElement;
  }

  @Input() set cIcon(value: readonly string[] | null | undefined) {
    if (value?.[0]) {
      this.element.setAttribute('viewBox', `0 0 ${value[0]}`);
    } else {
      this.element.removeAttribute('viewBox');
    }
    this.element.innerHTML = value?.[1] ?? '';
  }
}
