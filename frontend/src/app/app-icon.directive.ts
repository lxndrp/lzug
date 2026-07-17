import { Directive, ElementRef, Input } from '@angular/core';

@Directive({ selector: '[cIcon]' })
export class AppIconDirective {
  private readonly element: HTMLElement;

  constructor(element: ElementRef<HTMLElement>) {
    this.element = element.nativeElement;
  }

  @Input() set cIcon(value: readonly string[] | null | undefined) {
    this.element.innerHTML = value?.[1] ?? '';
  }
}
