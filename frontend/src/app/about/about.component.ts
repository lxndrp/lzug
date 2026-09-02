import { Component, Input } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';

@Component({
  selector: 'app-about',
  imports: [TuiButton],
  templateUrl: './about.component.html',
  styleUrl: './about.component.css',
})
export class AboutComponent {
  @Input() version: string | null = null;
  @Input() demo = false;
  @Input() demoMatrixVersion: string | null = null;
}
