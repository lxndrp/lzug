import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiButton, TuiDialogService, TuiIcon, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiInputDate, TuiPassword, TuiStepper } from '@taiga-ui/kit';

type PrototypeSection = 'planung' | 'prueflinge' | 'ausschuss';

@Component({
  selector: 'app-taiga-prototype',
  imports: [
    ReactiveFormsModule,
    TuiBadge,
    TuiButton,
    TuiIcon,
    TuiInput,
    TuiInputDate,
    TuiPassword,
    TuiStepper,
    TuiTable,
    TuiTextfield,
  ],
  templateUrl: './taiga-prototype.component.html',
  styleUrl: './taiga-prototype.component.scss',
})
export class TaigaPrototypeComponent {
  private readonly dialogs = inject(TuiDialogService);

  protected readonly activeSection = signal<PrototypeSection>('planung');
  protected readonly submitted = signal(false);
  protected readonly step = signal(1);
  protected readonly candidates = [
    {
      name: 'Lea Hoffmann',
      number: 'FI-2026-1042',
      specialization: 'Anwendungsentwicklung',
      status: 'Eingeplant',
    },
    {
      name: 'Jonas Weber',
      number: 'FI-2026-1057',
      specialization: 'Systemintegration',
      status: 'MEP erforderlich',
    },
    {
      name: 'Mina Yilmaz',
      number: 'FI-2026-1068',
      specialization: 'Daten- und Prozessanalyse',
      status: 'Offen',
    },
  ] as const;
  protected readonly days = [
    {
      date: 'Mo, 16.11.',
      location: 'HafenCity · 3.12',
      tone: 'good',
      slots: [
        ['08:30', 'Lea Hoffmann', 'vollständig'],
        ['10:00', 'Jonas Weber', '1 Vertretung'],
        ['13:00', 'Mina Yilmaz', 'vollständig'],
      ],
    },
    {
      date: 'Di, 17.11.',
      location: 'HafenCity · 3.12',
      tone: 'warn',
      slots: [
        ['08:30', 'Noah Fischer', '1 Prüfer fehlt'],
        ['10:00', 'Ella Nguyen', 'vollständig'],
      ],
    },
    {
      date: 'Mi, 18.11.',
      location: 'Nord · 2.04',
      tone: 'neutral',
      slots: [
        ['09:00', 'Freier Termin', 'verfügbar'],
        ['10:30', 'Freier Termin', 'verfügbar'],
      ],
    },
  ] as const;

  protected readonly form = new FormGroup({
    roundName: new FormControl('Winter 2026/27', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(4)],
    }),
    weekFrom: new FormControl('2026-W47', { nonNullable: true, validators: Validators.required }),
    sampleDate: new FormControl('', { nonNullable: true, validators: Validators.required }),
    password: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(8)],
    }),
  });

  protected submit(): void {
    this.submitted.set(true);
    this.form.markAllAsTouched();
  }

  protected openConfirmation(): void {
    this.dialogs
      .open(
        'Der aktuelle Vorschlag enthält 16 Prüfungen an drei Tagen. Dieser Dialog verändert keine Daten.',
        {
          label: 'Planungsvorschlag prüfen',
          size: 'm',
          dismissible: true,
        },
      )
      .subscribe();
  }
}
