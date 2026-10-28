import { describe, expect, test, vi } from 'vitest';
import type { FilesApi } from '../api';
import { filesystemFixture, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api';
import { FileDropState } from './file-drop-state.svelte';
import { FilesState } from './files-state.svelte';
import { UploadState } from './upload-state.svelte';

type TransferFields = Pick<DataTransfer, 'types' | 'files' | 'items' | 'dropEffect'>;

function fileItem(directory?: boolean): DataTransferItem {
  const item: Partial<DataTransferItem> = { kind: 'file', type: 'text/plain' };
  if (directory !== undefined) item.webkitGetAsEntry = vi.fn(() => ({ isDirectory: directory }) as FileSystemEntry);
  return item as DataTransferItem;
}

function dragEvent(types: string[] = ['Files'], files: File[] = [], items: DataTransferItem[] = []): DragEvent {
  const transfer: TransferFields = {
    types,
    files: Object.assign([...files], { item: (index: number): File | null => files[index] ?? null }),
    items: Object.assign([...items], {
      add: vi.fn(), clear: vi.fn(), remove: vi.fn()
    }),
    dropEffect: 'none'
  };
  return Object.defineProperty(new Event('drop', { cancelable: true }), 'dataTransfer', { value: transfer }) as DragEvent;
}

function fixture(): { drop: FileDropState; select: ReturnType<typeof vi.fn<(files: readonly File[]) => void>>; reject: ReturnType<typeof vi.fn<(message: string) => void>> } {
  const select = vi.fn<(files: readonly File[]) => void>();
  const reject = vi.fn<(message: string) => void>();
  return { drop: new FileDropState(select, reject, () => false), select, reject };
}

describe('file-only drag handling', () => {
  test.each([{ types: [] }, { types: ['text/plain'] }, { types: ['text/uri-list'] }, { types: ['text/plain', 'text/html'] }])('non-file transfer $types preserves native link and text handling', ({ types }): void => {
    const { drop, select, reject } = fixture();
    for (const action of [drop.enter, drop.over, drop.drop, drop.preventOutside]) {
      const event = dragEvent(types);
      action(event);
      expect(event.defaultPrevented).toBe(false);
      expect(event.dataTransfer?.dropEffect).toBe('none');
    }
    expect(drop.active).toBe(false);
    expect(select).not.toHaveBeenCalled();
    expect(reject).not.toHaveBeenCalled();
  });

  test('missing data transfer does not prevent native handling', (): void => {
    const { drop, select, reject } = fixture();
    const event = new Event('drop', { cancelable: true }) as DragEvent;
    drop.enter(event);
    drop.over(event);
    drop.drop(event);
    drop.preventOutside(event);
    expect(event.defaultPrevented).toBe(false);
    expect(select).not.toHaveBeenCalled();
    expect(reject).not.toHaveBeenCalled();
  });

  test('file drags prevent navigation, request copy and preserve activation across nested enter and leave', (): void => {
    const { drop } = fixture();
    const outer = dragEvent();
    drop.enter(outer);
    drop.enter(dragEvent());
    expect(outer.defaultPrevented).toBe(true);
    expect(drop.active).toBe(true);
    drop.leave();
    expect(drop.active).toBe(true);
    const over = dragEvent(['Files', 'text/plain']);
    drop.over(over);
    expect(over.defaultPrevented).toBe(true);
    expect(over.dataTransfer?.dropEffect).toBe('copy');
    drop.leave();
    drop.leave();
    expect(drop.active).toBe(false);
    drop.enter(dragEvent());
    expect(drop.active).toBe(true);
    drop.leave();
    expect(drop.active).toBe(false);
  });

  test('public reset cancels nested activation without selecting or rejecting and permits a fresh drag', (): void => {
    const { drop, select, reject } = fixture();
    drop.enter(dragEvent());
    drop.enter(dragEvent());
    expect(drop.active).toBe(true);
    drop.reset();
    drop.reset();
    expect(drop.active).toBe(false);
    expect(select).not.toHaveBeenCalled();
    expect(reject).not.toHaveBeenCalled();
    drop.leave();
    drop.enter(dragEvent());
    expect(drop.active).toBe(true);
    drop.leave();
    expect(drop.active).toBe(false);
    const file = new File([], 'After cancellation.txt');
    drop.drop(dragEvent(['Files'], [file], [fileItem()]));
    expect(select).toHaveBeenCalledExactlyOnceWith([file]);
    expect(reject).not.toHaveBeenCalled();
  });

  test('outside file drag resets nested activation and prevents browser file navigation with none effect', (): void => {
    const { drop, select } = fixture();
    drop.enter(dragEvent());
    drop.enter(dragEvent());
    const outside = dragEvent();
    if (outside.dataTransfer) outside.dataTransfer.dropEffect = 'copy';
    drop.preventOutside(outside);
    expect(outside.defaultPrevented).toBe(true);
    expect(outside.dataTransfer?.dropEffect).toBe('none');
    expect(drop.active).toBe(false);
    drop.enter(dragEvent());
    drop.leave();
    expect(drop.active).toBe(false);
    expect(select).not.toHaveBeenCalled();
  });

  test('outside handler leaves an already-handled drop alone', (): void => {
    const { drop } = fixture();
    drop.enter(dragEvent());
    const event = dragEvent();
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    drop.preventOutside(event);
    expect(event.dataTransfer?.dropEffect).toBe('copy');
    expect(drop.active).toBe(true);
  });

  test('drop resets depth and sends the whole single file selection once', (): void => {
    const { drop, select, reject } = fixture();
    const file = new File(['content'], 'Draft.txt');
    drop.enter(dragEvent());
    drop.enter(dragEvent());
    const event = dragEvent(['Files'], [file], [fileItem()]);
    drop.drop(event);
    expect(event.defaultPrevented).toBe(true);
    expect(drop.active).toBe(false);
    expect(select).toHaveBeenCalledExactlyOnceWith([file]);
    expect(reject).not.toHaveBeenCalled();
    drop.enter(dragEvent());
    drop.leave();
    expect(drop.active).toBe(false);
  });
});

describe('drop eligibility and rejection', () => {
  test.each([true, false])('folder entry detection rejects directories only when isDirectory is %s', (directory): void => {
    const { drop, select, reject } = fixture();
    const file = new File([], 'Entry');
    const item = fileItem(directory);
    drop.drop(dragEvent(['Files'], [file], [item]));
    expect(item.webkitGetAsEntry).toHaveBeenCalledTimes(1);
    if (directory) {
      expect(reject).toHaveBeenCalledWith(expect.stringMatching(/folders cannot be uploaded/i));
      expect(select).not.toHaveBeenCalled();
    } else {
      expect(select).toHaveBeenCalledWith([file]);
      expect(reject).not.toHaveBeenCalled();
    }
  });

  test('missing or null entry support still accepts an ordinary file', (): void => {
    for (const item of [fileItem(), { ...fileItem(), webkitGetAsEntry: (): null => null }]) {
      const { drop, select, reject } = fixture();
      const file = new File([], 'Empty.txt');
      drop.drop(dragEvent(['Files'], [file], [item]));
      expect(select).toHaveBeenCalledWith([file]);
      expect(reject).not.toHaveBeenCalled();
    }
  });

  test.each(['items', 'files', 'both'])('multiple %s are rejected as a whole rather than uploading the first', (source): void => {
    const { drop, select, reject } = fixture();
    const files = [new File([], 'One.txt'), new File([], 'Two.txt')];
    drop.drop(dragEvent(['Files'], source === 'items' ? [files[0]] : files, source === 'files' ? [fileItem()] : [fileItem(), fileItem()]));
    expect(reject).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/one file at a time/i));
    expect(select).not.toHaveBeenCalled();
    expect(drop.active).toBe(false);
  });

  test('unreadable transfer does not fabricate a valid empty file', (): void => {
    const { drop, select, reject } = fixture();
    drop.enter(dragEvent());
    drop.drop(dragEvent(['Files'], [], [fileItem()]));
    expect(reject).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/could not be read/i));
    expect(select).not.toHaveBeenCalled();
    expect(drop.active).toBe(false);
  });

  test('string items do not count as extra files in a mixed transfer', (): void => {
    const { drop, select, reject } = fixture();
    const file = new File(['x'], 'Mixed.txt');
    const text = { kind: 'string', type: 'text/plain' } as DataTransferItem;
    drop.drop(dragEvent(['Files', 'text/plain'], [file], [text, fileItem()]));
    expect(select).toHaveBeenCalledExactlyOnceWith([file]);
    expect(reject).not.toHaveBeenCalled();
  });

  test('disabled drop never activates, selects or rejects and requests none instead of copy', (): void => {
    const select = vi.fn();
    const reject = vi.fn();
    const drop = new FileDropState(select, reject, () => true);
    const enter = dragEvent();
    drop.enter(enter);
    expect(drop.active).toBe(false);
    expect(enter.defaultPrevented).toBe(false);
    const over = dragEvent();
    drop.over(over);
    expect(over.defaultPrevented).toBe(true);
    expect(over.dataTransfer?.dropEffect).toBe('none');
    const event = dragEvent(['Files'], [new File([], 'Empty.txt')], [fileItem()]);
    drop.drop(event);
    expect(event.defaultPrevented).toBe(true);
    expect(select).not.toHaveBeenCalled();
    expect(reject).not.toHaveBeenCalled();
  });

  test('becoming disabled during a drag resets activation on drop without selecting', (): void => {
    let disabled = false;
    const select = vi.fn();
    const drop = new FileDropState(select, vi.fn(), () => disabled);
    drop.enter(dragEvent());
    expect(drop.active).toBe(true);
    disabled = true;
    drop.drop(dragEvent(['Files'], [new File([], 'Empty.txt')]));
    expect(drop.active).toBe(false);
    expect(select).not.toHaveBeenCalled();
  });

  test('zero-byte drop and chooser selection use the same public UploadState pipeline', async (): Promise<void> => {
    const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture, { max_bytes: 8 });
    const files = new FilesState(api);
    const upload = new UploadState(api, files);
    await files.load(null);
    await vi.waitFor(() => expect(upload.available).toBe(true));
    upload.show();
    const select = vi.spyOn(upload, 'select');
    const drop = new FileDropState(upload.select, upload.rejectSelection, () => upload.pending || upload.uncertain);
    const file = new File([], 'Empty.txt');
    upload.select([file]);
    const chooserStatus = upload.status;
    expect(upload.canSubmit).toBe(true);
    upload.remove();
    drop.drop(dragEvent(['Files'], [file], [fileItem()]));
    expect(select).toHaveBeenNthCalledWith(1, [file]);
    expect(select).toHaveBeenNthCalledWith(2, [file]);
    expect(upload.file).toBe(file);
    expect(upload.name).toBe(file.name);
    expect(upload.status).toBe(chooserStatus);
    expect(upload.canSubmit).toBe(true);
  });
});
