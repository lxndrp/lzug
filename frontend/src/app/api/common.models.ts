import type { ApiRootResponse, DomainCollectionResponse } from './generated/types.gen';

/** A HAL-like link. The optional method describes an allowed state transition. */
export type ApiLink = {
  href: string;
  method?: string;
};

export type ApiRoot = ApiRootResponse & {
  _links: Record<string, ApiLink>;
};

export type ApiCollection<T> = Omit<DomainCollectionResponse, 'items' | '_links'> & {
  items: T[];
  _links: Record<string, ApiLink>;
};
