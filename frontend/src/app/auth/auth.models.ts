import { InjectionToken } from '@angular/core';

export type AuthState = 'checking' | 'authenticated' | 'anonymous';

export interface AuthenticationPort {
  markAnonymous(): void;
}

export const AUTHENTICATION_PORT = new InjectionToken<AuthenticationPort>('AUTHENTICATION_PORT');

export type AuthSession = {
  account_id: number;
  authenticated: boolean;
  capabilities?: string[] | null;
  committee_member_id: number | null;
  demo_matrix_version?: string | null;
  demo_role?: 'chair' | 'examiner' | 'replacement' | null;
  demo_workspace_expires_at?: string | null;
  display_name?: string | null;
  is_operator: boolean;
  person_id: number | null;
};

export type AuthPreparation = {
  email: string;
  expires_at: string;
  totp_secret?: string;
};

export type AuthCompletion = {
  activated?: boolean;
  recovered?: boolean;
  account: { id: number; email: string; is_operator: boolean };
  recovery_codes: string[];
};

export type LoginCredentials = {
  email: string;
  password: string;
  second_factor: string;
};

export type InvitationCommand = { token: string };

export type FactorActivationCommand = {
  token: string;
  password: string;
  totp_secret: string;
  totp_code: string;
};
