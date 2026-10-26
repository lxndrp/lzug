import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

/** The build identity shown on the product-information page. */
export interface BuildInfoPort {
  loadVersion(): Observable<string>;
}

export const BUILD_INFO_PORT = new InjectionToken<BuildInfoPort>('BUILD_INFO_PORT');
