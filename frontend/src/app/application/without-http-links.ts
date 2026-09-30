/** Remove transport navigation links from a value at an application boundary. */
export type WithoutHttpLinks<T> = T extends readonly (infer Item)[]
  ? WithoutHttpLinks<Item>[]
  : T extends object
    ? { [Key in keyof T as Key extends '_links' ? never : Key]: WithoutHttpLinks<T[Key]> }
    : T;

export function withoutHttpLinks<T>(value: T): WithoutHttpLinks<T> {
  if (Array.isArray(value)) {
    return value.map((item: unknown) => withoutHttpLinks(item)) as WithoutHttpLinks<T>;
  }
  if (typeof value !== 'object' || value === null) {
    return value as WithoutHttpLinks<T>;
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => key !== '_links')
      .map(([key, item]) => [key, withoutHttpLinks(item)]),
  ) as WithoutHttpLinks<T>;
}
