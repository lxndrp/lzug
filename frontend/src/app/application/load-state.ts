/** A resource load state that keeps refresh data explicit. */
export type LoadState<T> =
  | { status: 'loading'; previous: T | null }
  | { status: 'ready'; data: T }
  | { status: 'error'; previous: T | null }
  | { status: 'not-found'; previous: T | null };

/** Returns data retained while a resource is refreshing or showing a load error. */
export function loadStateValue<T>(state: LoadState<T>): T | null {
  switch (state.status) {
    case 'ready':
      return state.data;
    case 'loading':
    case 'error':
    case 'not-found':
      return state.previous;
  }
}
