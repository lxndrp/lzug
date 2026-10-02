import { Injectable, inject, signal } from '@angular/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { finalize, Observable, takeUntil } from 'rxjs';
import { SessionScopeService } from '../auth/session-scope.service';

export type UiFeedback = {
  type: 'success' | 'error';
  title: string;
  message: string;
};

/** Shared confirmation and transient feedback boundary for feature workflows. */
@Injectable({ providedIn: 'root' })
export class UiFeedbackService {
  private readonly confirmService = inject(TuiConfirmService);
  private readonly sessionScope = inject(SessionScopeService);

  readonly feedback = signal<UiFeedback | null>(null);

  constructor() {
    this.sessionScope.changes$.subscribe(() => this.dismiss());
  }

  notify(type: UiFeedback['type'], title: string, message: string): void {
    this.feedback.set({ type, title, message });
  }

  dismiss(): void {
    this.feedback.set(null);
  }

  confirm(title: string, message: string, confirmLabel: string, action: () => void): void {
    this.confirm$(title, message, confirmLabel).subscribe((confirmed) => {
      if (confirmed) action();
    });
  }

  confirm$(title: string, message: string, confirmLabel: string): Observable<boolean> {
    const generation = this.sessionScope.generation();
    this.confirmService.markAsDirty();
    return this.confirmService
      .withConfirm({
        label: title,
        size: 'm',
        data: { content: message, no: 'Abbrechen', yes: confirmLabel, appearance: 'negative' },
      })
      .pipe(takeUntil(this.sessionScope.invalidatedAfter(generation)))
      .pipe(finalize(() => this.confirmService.markAsPristine()));
  }

  roleRestriction(): void {
    this.notify(
      'error',
      'Aktion für diese Rolle nicht verfügbar',
      'Bitte öffnen Sie den für Ihre Demo-Rolle vorgesehenen Aufgabenpfad.',
    );
  }
}
