/** A HAL-like link. The optional method describes an allowed state transition. */
export type ApiLink = {
  href: string;
  method?: string;
};

export type ApiRoot = {
  name: string;
  version: string;
  _links: Record<string, ApiLink>;
};

export type ApiCollection<T> = {
  items: T[];
  _links: Record<string, ApiLink>;
};
