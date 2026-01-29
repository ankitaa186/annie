/**
 * Tests for fileValidation utilities
 */

import { describe, it, expect } from 'vitest';
import {
  formatBytes,
  validateFile,
  validateFiles,
  isImageFile,
  getFileIconType,
  getAcceptAttribute,
  SUPPORTED_MIME_TYPES,
  MAX_FILES_PER_MESSAGE,
  CHAR_COUNT_VISIBLE_THRESHOLD,
  CHAR_COUNT_WARNING_THRESHOLD,
  CHAR_COUNT_MAX_THRESHOLD,
} from '../fileValidation';

// Helper to create mock File objects
function createMockFile(
  name: string,
  type: string,
  size: number
): File {
  const content = new Array(size).fill('a').join('');
  return new File([content], name, { type });
}

describe('formatBytes', () => {
  it('should format 0 bytes', () => {
    expect(formatBytes(0)).toBe('0 Bytes');
  });

  it('should format bytes', () => {
    expect(formatBytes(500)).toBe('500 Bytes');
  });

  it('should format kilobytes', () => {
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(2048)).toBe('2 KB');
  });

  it('should format megabytes', () => {
    expect(formatBytes(1024 * 1024)).toBe('1 MB');
    expect(formatBytes(10 * 1024 * 1024)).toBe('10 MB');
  });

  it('should respect decimal places', () => {
    expect(formatBytes(1536, 2)).toBe('1.5 KB');
  });
});

describe('validateFile', () => {
  it('should accept valid image files', () => {
    const file = createMockFile('test.jpg', 'image/jpeg', 1000);
    const result = validateFile(file);
    expect(result.valid).toBe(true);
    expect(result.error).toBeUndefined();
  });

  it('should accept valid PDF files', () => {
    const file = createMockFile('test.pdf', 'application/pdf', 5000);
    const result = validateFile(file);
    expect(result.valid).toBe(true);
  });

  it('should reject unsupported file types', () => {
    const file = createMockFile('test.exe', 'application/x-msdownload', 1000);
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('not supported');
  });

  it('should reject oversized images', () => {
    const file = createMockFile('huge.jpg', 'image/jpeg', 15 * 1024 * 1024); // 15MB
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('too large');
  });

  it('should reject oversized documents', () => {
    const file = createMockFile('huge.pdf', 'application/pdf', 25 * 1024 * 1024); // 25MB
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('too large');
  });

  it('should reject empty files', () => {
    const file = createMockFile('empty.jpg', 'image/jpeg', 0);
    const result = validateFile(file);
    expect(result.valid).toBe(false);
    expect(result.error).toContain('empty');
  });
});

describe('validateFiles', () => {
  it('should accept valid files within limit', () => {
    const files = [
      createMockFile('a.jpg', 'image/jpeg', 1000),
      createMockFile('b.png', 'image/png', 2000),
    ];
    const result = validateFiles(files);
    expect(result.valid).toHaveLength(2);
    expect(result.errors).toHaveLength(0);
  });

  it('should respect existing file count', () => {
    const files = [createMockFile('a.jpg', 'image/jpeg', 1000)];
    const result = validateFiles(files, 10); // Already at max
    expect(result.valid).toHaveLength(0);
    expect(result.errors).toContain(`Maximum ${MAX_FILES_PER_MESSAGE} files per message. Remove some files first.`);
  });

  it('should limit files when exceeding max', () => {
    const files = Array.from({ length: 15 }, (_, i) =>
      createMockFile(`file${i}.jpg`, 'image/jpeg', 1000)
    );
    const result = validateFiles(files);
    expect(result.valid.length).toBeLessThanOrEqual(MAX_FILES_PER_MESSAGE);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it('should accumulate errors for invalid files', () => {
    const files = [
      createMockFile('valid.jpg', 'image/jpeg', 1000),
      createMockFile('invalid.exe', 'application/x-msdownload', 1000),
      createMockFile('huge.jpg', 'image/jpeg', 15 * 1024 * 1024),
    ];
    const result = validateFiles(files);
    expect(result.valid).toHaveLength(1);
    expect(result.errors).toHaveLength(2);
  });
});

describe('isImageFile', () => {
  it('should return true for images', () => {
    expect(isImageFile(createMockFile('a.jpg', 'image/jpeg', 100))).toBe(true);
    expect(isImageFile(createMockFile('a.png', 'image/png', 100))).toBe(true);
    expect(isImageFile(createMockFile('a.gif', 'image/gif', 100))).toBe(true);
    expect(isImageFile(createMockFile('a.webp', 'image/webp', 100))).toBe(true);
  });

  it('should return false for non-images', () => {
    expect(isImageFile(createMockFile('a.pdf', 'application/pdf', 100))).toBe(false);
    expect(isImageFile(createMockFile('a.txt', 'text/plain', 100))).toBe(false);
    expect(isImageFile(createMockFile('a.csv', 'text/csv', 100))).toBe(false);
  });
});

describe('getFileIconType', () => {
  it('should return correct icon type for images', () => {
    expect(getFileIconType('image/jpeg')).toBe('image');
    expect(getFileIconType('image/png')).toBe('image');
  });

  it('should return correct icon type for PDFs', () => {
    expect(getFileIconType('application/pdf')).toBe('pdf');
  });

  it('should return correct icon type for Word docs', () => {
    expect(
      getFileIconType('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    ).toBe('doc');
  });

  it('should return correct icon type for spreadsheets', () => {
    expect(getFileIconType('text/csv')).toBe('spreadsheet');
    expect(
      getFileIconType('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    ).toBe('spreadsheet');
  });

  it('should return correct icon type for text files', () => {
    expect(getFileIconType('text/plain')).toBe('text');
  });

  it('should return file for unknown types', () => {
    expect(getFileIconType('application/octet-stream')).toBe('file');
  });
});

describe('getAcceptAttribute', () => {
  it('should return comma-separated MIME types', () => {
    const accept = getAcceptAttribute();
    expect(accept).toContain('image/jpeg');
    expect(accept).toContain('image/png');
    expect(accept).toContain('application/pdf');
    expect(accept.split(',')).toHaveLength(Object.keys(SUPPORTED_MIME_TYPES).length);
  });
});

describe('constants', () => {
  it('should have correct character count thresholds', () => {
    expect(CHAR_COUNT_VISIBLE_THRESHOLD).toBe(500);
    expect(CHAR_COUNT_WARNING_THRESHOLD).toBe(4000);
    expect(CHAR_COUNT_MAX_THRESHOLD).toBe(8000);
  });

  it('should have correct max files limit', () => {
    expect(MAX_FILES_PER_MESSAGE).toBe(10);
  });

  it('should have correct size limits in SUPPORTED_MIME_TYPES', () => {
    // Images should be 10MB
    expect(SUPPORTED_MIME_TYPES['image/jpeg'].maxSize).toBe(10 * 1024 * 1024);
    expect(SUPPORTED_MIME_TYPES['image/png'].maxSize).toBe(10 * 1024 * 1024);

    // Documents should be 20MB
    expect(SUPPORTED_MIME_TYPES['application/pdf'].maxSize).toBe(20 * 1024 * 1024);
    expect(SUPPORTED_MIME_TYPES['text/plain'].maxSize).toBe(20 * 1024 * 1024);
  });
});
