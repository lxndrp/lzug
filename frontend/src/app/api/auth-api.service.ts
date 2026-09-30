import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type {
  AuthCompletion,
  AuthPreparation,
  AuthSession,
  FactorActivationCommand,
  InvitationCommand,
  LoginCredentials,
} from '../auth/auth.models';
import { ApiClient } from './api-client.service';
import type {
  FactorActivationRequest,
  LoginRequest,
  SessionResponse,
  TokenRequest,
} from './generated/types.gen';

/** Authentication HTTP adapter. Session policy remains in AuthService. */
@Injectable({ providedIn: 'root' })
export class AuthApiService {
  private readonly client = inject(ApiClient);

  session() {
    return this.client.get<SessionResponse>('/api/session').pipe(
      map((session): AuthSession => ({
        account_id: session.account_id,
        authenticated: session.authenticated,
        capabilities: session.capabilities,
        committee_member_id: session.committee_member_id,
        demo_matrix_version: session.demo_matrix_version,
        demo_role: session.demo_role,
        demo_workspace_expires_at: session.demo_workspace_expires_at,
        display_name: session.display_name,
        is_operator: session.is_operator,
        person_id: session.person_id,
      })),
    );
  }

  login(credentials: LoginCredentials) {
    const request = {
      email: credentials.email,
      password: credentials.password,
      second_factor: credentials.second_factor,
    } satisfies LoginRequest;
    return this.client.post<{ authenticated: true; account_id: number; expires_at: string }>(
      '/api/auth/login',
      request,
    );
  }

  logout() {
    return this.client.post<void>('/api/session/logout', {});
  }

  prepareInvitation(command: InvitationCommand) {
    return this.client.post<AuthPreparation>(
      '/api/auth/invitation/prepare',
      command satisfies TokenRequest,
    );
  }

  activateInvitation(command: FactorActivationCommand) {
    return this.client.post<AuthCompletion>(
      '/api/auth/invitation/activate',
      command satisfies FactorActivationRequest,
    );
  }

  prepareRecovery(command: InvitationCommand) {
    return this.client.post<AuthPreparation>(
      '/api/auth/recovery/prepare',
      command satisfies TokenRequest,
    );
  }

  completeRecovery(command: FactorActivationCommand) {
    return this.client.post<AuthCompletion>(
      '/api/auth/recovery/complete',
      command satisfies FactorActivationRequest,
    );
  }
}
