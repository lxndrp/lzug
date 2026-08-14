import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';

type DemoStatus = {
  product_version: string;
  next_reset_at: string;
  reset_timezone: string;
};

@Component({
  selector: 'app-runtime-notice',
  template: `
    <aside class="demo-notice" aria-label="Hinweis zur flüchtigen Demo">
      <strong>Flüchtige Demo</strong>
      <span>Keine realen personenbezogenen Daten eingeben.</span>
      @if (status(); as current) {
        <span
          >Nächster Reset: {{ resetLabel(current.next_reset_at) }} · Version
          {{ current.product_version }}</span
        >
      } @else {
        <span>Reset täglich um 03:00 Uhr Europe/Berlin.</span>
      }
    </aside>
  `,
  styles: `
    .demo-notice {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0.35rem 1.25rem;
      padding: 0.65rem 1rem;
      border-bottom: 1px solid #d9a548;
      color: #3d2a00;
      background: #fff3dc;
      font-size: 0.9rem;
      line-height: 1.35;
      text-align: center;
    }
  `,
})
export class RuntimeNoticeComponent {
  private readonly http = inject(HttpClient);
  protected readonly status = signal<DemoStatus | null>(null);

  constructor() {
    this.http.get<DemoStatus>('/api/demo/status').subscribe({
      next: (status) => this.status.set(status),
    });
  }

  protected resetLabel(timestamp: string): string {
    return new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short',
      timeZone: 'Europe/Berlin',
    }).format(new Date(timestamp));
  }
}
