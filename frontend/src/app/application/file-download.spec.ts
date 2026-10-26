import { downloadFile } from './file-download';

describe('downloadFile', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts a browser download with the returned content, media type, and file name', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:export');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    let clickedLink: { href: string; download: string } | undefined;
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedLink = { href: this.href, download: this.download };
    });
    let revoke: (() => void) | undefined;
    const setTimeout = vi.spyOn(window, 'setTimeout').mockImplementation((callback) => {
      if (typeof callback === 'function') revoke = callback as () => void;
      return 1;
    });

    downloadFile({ content: 'export data', mediaType: 'text/plain', fileName: 'result.txt' });

    const blob = createObjectURL.mock.calls[0]?.[0];
    expect(blob).toBeInstanceOf(Blob);
    expect((blob as Blob | undefined)?.type).toBe('text/plain');
    expect(await (blob as Blob).text()).toBe('export data');
    expect(clickedLink).toEqual({ href: 'blob:export', download: 'result.txt' });
    expect(setTimeout).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();

    revoke?.();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export');
  });
});
