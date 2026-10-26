/** File contents returned by a domain export operation. */
export type FileDownload = {
  content: string;
  mediaType: string;
  fileName: string;
};

/** Starts a browser download for an already authorized and materialized export. */
export function downloadFile(file: FileDownload): void {
  const url = URL.createObjectURL(new Blob([file.content], { type: file.mediaType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = file.fileName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
