import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, map, throwError } from 'rxjs';

import { toApplicationError } from './application-error';
import { ApiCollection } from './common.models';

/** Shared HTTP and collection transport for all domain API clients. */
@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  get<T>(url: string) {
    return this.adapt(this.http.get<T>(url));
  }

  post<T>(url: string, body: unknown) {
    return this.adapt(this.http.post<T>(url, body));
  }

  patch<T>(url: string, body: unknown) {
    return this.adapt(this.http.patch<T>(url, body));
  }

  put<T>(url: string, body: unknown) {
    return this.adapt(this.http.put<T>(url, body));
  }

  delete<T>(url: string, options?: { body?: unknown }) {
    return this.adapt(this.http.delete<T>(url, options));
  }

  list<T>(url: string) {
    return this.get<ApiCollection<T>>(url).pipe(map((collection) => collection.items));
  }

  collection<T>(url: string) {
    return this.get<ApiCollection<T>>(url);
  }

  private adapt<T>(request: Observable<T>): Observable<T> {
    return request.pipe(
      catchError((error: unknown) => throwError(() => toApplicationError(error))),
    );
  }
}
