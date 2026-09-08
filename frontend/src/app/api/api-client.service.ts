import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { ApiCollection } from './common.models';

/** Shared HTTP and collection transport for all domain API clients. */
@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  get<T>(url: string) {
    return this.http.get<T>(url);
  }

  post<T>(url: string, body: unknown) {
    return this.http.post<T>(url, body);
  }

  patch<T>(url: string, body: unknown) {
    return this.http.patch<T>(url, body);
  }

  put<T>(url: string, body: unknown) {
    return this.http.put<T>(url, body);
  }

  delete<T>(url: string, options?: { body?: unknown }) {
    return this.http.delete<T>(url, options);
  }

  list<T>(url: string) {
    return this.get<ApiCollection<T>>(url).pipe(map((collection) => collection.items));
  }

  collection<T>(url: string) {
    return this.get<ApiCollection<T>>(url);
  }
}
