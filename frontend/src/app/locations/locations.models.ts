export type VenueScope = 'global' | 'committee';
export type VenueAccessibilityStatus = 'confirmed' | 'needs_clarification';
export type VenueCoordinateStatus = 'missing' | 'needs_review' | 'confirmed';

export type CommitteeSummary = { id: number; name: string };

export type LocationSnapshot = {
  committees: CommitteeSummary[];
  venues: Venue[];
  canCreateVenue: boolean;
};

export type VenueRoom = {
  id: number;
  venueId: number;
  name: string;
  building: string | null;
  wing: string | null;
  floor: string | null;
  roomNumber: string | null;
  accessNotes: string | null;
  capacity: number | null;
  isActive: boolean;
  revision: number;
  consequenceWarning?: string;
};

export type VenueContact = {
  id: number;
  venueId: number;
  label: string;
  role: string | null;
  phone: string | null;
  email: string | null;
  availabilityNotes: string | null;
  isActive: boolean;
  revision: number;
  roomIds: number[];
};

export type VenueConsequenceProblem = {
  auditId: number;
  venueId: number;
  entityType: 'venue' | 'room';
  entityId: number;
  consequenceType: 'calendar' | 'notification' | 'derivation';
  status: 'temporarily_failed' | 'permanently_failed';
  attemptCount: number;
  errorCode: string | null;
  updatedAt: string;
};

export type Venue = {
  id: number;
  scope: VenueScope;
  committeeId: number | null;
  name: string;
  street: string;
  postalCode: string;
  city: string;
  country: string;
  siteName: string | null;
  entrance: string | null;
  travelDirections: string | null;
  isAccessible: boolean | null;
  accessibilityStatus: VenueAccessibilityStatus;
  accessibilityNotes: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinateStatus: VenueCoordinateStatus;
  coordinateSource: string | null;
  isActive: boolean;
  revision: number;
  consequenceWarning?: string;
  rooms: VenueRoom[];
  contacts: VenueContact[];
  consequenceProblems: VenueConsequenceProblem[];
  mapProvider: {
    mode: 'off' | 'osm' | 'google';
    attribution?: string;
    attributionUrl?: string;
  };
  capabilities: {
    manage: boolean;
    retryConsequences?: boolean;
    geocode?: boolean;
    requestPromotion: boolean;
    decidePromotion: boolean;
  };
};

export type VenueCreate = {
  scope: VenueScope;
  committeeId: number | null;
  name: string;
  street: string;
  postalCode: string;
  city: string;
  country: string;
  siteName?: string | null;
  entrance?: string | null;
  travelDirections?: string | null;
  accessibilityStatus: VenueAccessibilityStatus;
  isAccessible: boolean | null;
  accessibilityNotes?: string | null;
  isActive: boolean;
  latitude?: number | null;
  longitude?: number | null;
  coordinateStatus?: VenueCoordinateStatus;
  coordinateSource?: string | null;
  duplicateReason?: string;
  meaningfulChange?: boolean;
};

export type VenueUpdate = {
  id: number;
  payload: Partial<VenueCreate> & { expectedRevision: number };
};

export type VenueRoomDraft = {
  name: string;
  building?: string | null;
  wing?: string | null;
  floor?: string | null;
  roomNumber?: string | null;
  accessNotes?: string | null;
  capacity: number | null;
  isActive?: boolean;
  meaningfulChange?: boolean;
};

export type VenueRoomCreate = {
  venueId: number;
  payload: VenueRoomDraft & { isActive: boolean };
};

export type VenueRoomUpdate = {
  id: number;
  payload: Partial<VenueRoomDraft> & { expectedRevision: number };
};

export type VenueContactDraft = {
  label: string;
  email: string | null;
  phone: string | null;
  availabilityNotes: string | null;
  isActive: boolean;
};

export type VenueContactCreate = { venueId: number; payload: VenueContactDraft };
export type VenueContactUpdate = {
  id: number;
  payload: Partial<VenueContactDraft> & { expectedRevision: number };
};

export type GeocodeCandidate = {
  venueId: number;
  latitude: number;
  longitude: number;
  source: string;
};

export type VenueDuplicate = { id: number; name: string; scope: string; address: string };
export type VenueChangeImpact = {
  count: number;
  dateFrom: string | null;
  dateTo: string | null;
  requiresConfirmation: boolean;
  calendar: { eventCount: number; fields: string[] };
  notifications: { recipientCount: number; fields: string[] };
};
export type VenueConsequenceResult = {
  auditId: number;
  processed: number;
  problems: number;
  pending: number;
  superseded: number;
};
