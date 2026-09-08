import { Injectable, inject, signal } from '@angular/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { finalize } from 'rxjs';

export type UiFeedback = {
  type: 'success' | 'error';
  title: string;
  message: string;
};

/** Shared confirmation and transient feedback boundary for feature workflows. */
@Injectable({ providedIn: 'root' })
export class UiFeedbackService {
  private readonly confirmService = inject(TuiConfirmService);

  readonly feedback = signal<UiFeedback | null>(null);

  notify(type: UiFeedback['type'], title: string, message: string): void {
    this.feedback.set({ type, title, message });
  }

  dismiss(): void {
    this.feedback.set(null);
  }

  confirm(title: string, message: string, confirmLabel: string, action: () => void): void {
    this.confirmService.markAsDirty();
    this.confirmService
      .withConfirm({
        label: title,
        size: 'm',
        data: { content: message, no: 'Abbrechen', yes: confirmLabel, appearance: 'negative' },
      })
      .pipe(finalize(() => this.confirmService.markAsPristine()))
      .subscribe((confirmed) => {
        if (confirmed) action();
      });
  }

  roleRestriction(): void {
    this.notify(
      'error',
      'Aktion für diese Rolle nicht verfügbar',
      'Bitte öffnen Sie den für Ihre Demo-Rolle vorgesehenen Aufgabenpfad.',
    );
  }
}
