/**
 * File validation utilities for chat file uploads
 *
 * Mirrors backend file_attachment.py validation rules for consistency.
 * Supports images (10MB), documents (20MB), spreadsheets (20MB), max 10 files.
 */

/** File category for size limit determination */
export type FileCategory = 'image' | 'document' | 'spreadsheet';

/** MIME type configuration with size limits */
export interface MimeTypeConfig {
  category: FileCategory;
  maxSize: number; // bytes
  label: string;
}

/** Supported MIME types with their configurations */
export const SUPPORTED_MIME_TYPES: Record<string, MimeTypeConfig> = {
  // Images (10MB max)
  'image/jpeg': { category: 'image', maxSize: 10 * 1024 * 1024, label: 'JPEG' },
  'image/png': { category: 'image', maxSize: 10 * 1024 * 1024, label: 'PNG' },
  'image/gif': { category: 'image', maxSize: 10 * 1024 * 1024, label: 'GIF' },
  'image/webp': { category: 'image', maxSize: 10 * 1024 * 1024, label: 'WebP' },

  // Documents (20MB max)
  'application/pdf': { category: 'document', maxSize: 20 * 1024 * 1024, label: 'PDF' },
  'text/plain': { category: 'document', maxSize: 20 * 1024 * 1024, label: 'Text' },
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {
    category: 'document',
    maxSize: 20 * 1024 * 1024,
    label: 'Word',
  },

  // Spreadsheets (20MB max)
  'text/csv': { category: 'spreadsheet', maxSize: 20 * 1024 * 1024, label: 'CSV' },
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': {
    category: 'spreadsheet',
    maxSize: 20 * 1024 * 1024,
    label: 'Excel',
  },
};

/** Maximum files per message */
export const MAX_FILES_PER_MESSAGE = 10;

/** Character count thresholds */
export const CHAR_COUNT_VISIBLE_THRESHOLD = 500;
export const CHAR_COUNT_WARNING_THRESHOLD = 4000;
export const CHAR_COUNT_MAX_THRESHOLD = 8000;

/**
 * Format bytes to human-readable string
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i];
}

/**
 * Validation result for a single file
 */
export interface FileValidationResult {
  valid: boolean;
  error?: string;
  file: File;
}

/**
 * Validate a single file against MIME type and size limits
 */
export function validateFile(file: File): FileValidationResult {
  const config = SUPPORTED_MIME_TYPES[file.type];

  // Check if MIME type is supported
  if (!config) {
    const extension = file.name.split('.').pop()?.toLowerCase() || 'unknown';
    return {
      valid: false,
      error: `File type not supported: .${extension}. Supported: images, PDFs, Word docs, Excel, CSV, and text files.`,
      file,
    };
  }

  // Check file size
  if (file.size > config.maxSize) {
    return {
      valid: false,
      error: `"${file.name}" is too large (${formatBytes(file.size)}). Maximum for ${config.label}: ${formatBytes(config.maxSize)}.`,
      file,
    };
  }

  // Check if file is empty
  if (file.size === 0) {
    return {
      valid: false,
      error: `"${file.name}" is empty.`,
      file,
    };
  }

  return { valid: true, file };
}

/**
 * Validate multiple files including the total count limit
 */
export function validateFiles(
  files: File[],
  existingCount = 0
): { valid: File[]; errors: string[] } {
  const errors: string[] = [];
  const valid: File[] = [];

  // Check total count
  const totalCount = existingCount + files.length;
  if (totalCount > MAX_FILES_PER_MESSAGE) {
    const remaining = MAX_FILES_PER_MESSAGE - existingCount;
    if (remaining <= 0) {
      errors.push(`Maximum ${MAX_FILES_PER_MESSAGE} files per message. Remove some files first.`);
    } else {
      errors.push(
        `Can only add ${remaining} more file${remaining !== 1 ? 's' : ''}. Maximum ${MAX_FILES_PER_MESSAGE} files per message.`
      );
    }
    // Only validate files that would fit
    files = files.slice(0, Math.max(0, remaining));
  }

  // Validate each file
  for (const file of files) {
    const result = validateFile(file);
    if (result.valid) {
      valid.push(result.file);
    } else if (result.error) {
      errors.push(result.error);
    }
  }

  return { valid, errors };
}

/**
 * Check if a file is an image
 */
export function isImageFile(file: File): boolean {
  return file.type.startsWith('image/');
}

/**
 * Get file icon type based on MIME type
 */
export function getFileIconType(
  mimeType: string
): 'image' | 'pdf' | 'doc' | 'spreadsheet' | 'text' | 'file' {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType === 'application/pdf') return 'pdf';
  if (mimeType.includes('wordprocessingml')) return 'doc';
  if (mimeType.includes('spreadsheetml') || mimeType === 'text/csv') return 'spreadsheet';
  if (mimeType === 'text/plain') return 'text';
  return 'file';
}

/**
 * Generate accept attribute for file input
 */
export function getAcceptAttribute(): string {
  return Object.keys(SUPPORTED_MIME_TYPES).join(',');
}

/**
 * Convert a File to base64 string
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Remove data URL prefix (e.g., "data:image/png;base64,")
      const base64 = result.split(',')[1] ?? '';
      resolve(base64);
    };
    reader.onerror = () => reject(new Error(`Failed to read file: ${file.name}`));
    reader.readAsDataURL(file);
  });
}

/**
 * FileAttachment interface matching backend API
 */
export interface FileAttachment {
  filename: string;
  mime_type: string;
  size_bytes: number;
  data_base64: string;
}

/**
 * Convert File to FileAttachment for API
 */
export async function fileToAttachment(file: File): Promise<FileAttachment> {
  const base64 = await fileToBase64(file);
  return {
    filename: file.name,
    mime_type: file.type,
    size_bytes: file.size,
    data_base64: base64,
  };
}

/**
 * Convert multiple Files to FileAttachments
 */
export async function filesToAttachments(files: File[]): Promise<FileAttachment[]> {
  return Promise.all(files.map(fileToAttachment));
}
