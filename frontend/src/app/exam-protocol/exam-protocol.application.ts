import { Injectable, inject } from '@angular/core';

import { EXAM_PROTOCOL_PORT } from './exam-protocol.port';

/** Application operations for reading and managing exam protocols. */
@Injectable({ providedIn: 'root' })
export class ExamProtocolApplication {
  private readonly port = inject(EXAM_PROTOCOL_PORT);

  get(...args: Parameters<typeof this.port.get>) {
    return this.port.get(...args);
  }

  update(...args: Parameters<typeof this.port.update>) {
    return this.port.update(...args);
  }

  submit(...args: Parameters<typeof this.port.submit>) {
    return this.port.submit(...args);
  }

  respond(...args: Parameters<typeof this.port.respond>) {
    return this.port.respond(...args);
  }

  requestCorrection(...args: Parameters<typeof this.port.requestCorrection>) {
    return this.port.requestCorrection(...args);
  }

  openCorrection(...args: Parameters<typeof this.port.openCorrection>) {
    return this.port.openCorrection(...args);
  }

  export(...args: Parameters<typeof this.port.export>) {
    return this.port.export(...args);
  }
}
