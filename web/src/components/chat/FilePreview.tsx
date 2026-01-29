/**
 * FilePreview component
 *
 * Displays file previews before sending. Shows thumbnails for images,
 * icons for other file types. Allows removing files.
 */

import { useMemo, useEffect } from 'react';
import { X, FileText, FileSpreadsheet, File, FileImage } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatBytes, getFileIconType } from '@/lib/utils/fileValidation';

interface FilePreviewProps {
  files: File[];
  onRemove: (index: number) => void;
  disabled?: boolean;
}

const fileIcons = {
  image: FileImage,
  pdf: FileText,
  doc: FileText,
  spreadsheet: FileSpreadsheet,
  text: FileText,
  file: File,
} as const;

interface SingleFilePreviewProps {
  file: File;
  index: number;
  onRemove: (index: number) => void;
  disabled?: boolean;
}

function SingleFilePreview({ file, index, onRemove, disabled }: SingleFilePreviewProps) {
  const iconType = getFileIconType(file.type);
  const Icon = fileIcons[iconType];

  // Create object URL for image preview
  const imageUrl = useMemo(() => {
    if (iconType === 'image') {
      return URL.createObjectURL(file);
    }
    return null;
  }, [file, iconType]);

  // Cleanup object URL on unmount
  useEffect(() => {
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, [imageUrl]);

  return (
    <div
      className={cn(
        'relative group flex-shrink-0',
        'w-16 h-16 rounded-lg overflow-hidden',
        'border border-border bg-muted',
        'transition-all duration-200',
        disabled && 'opacity-50'
      )}
      title={`${file.name} (${formatBytes(file.size)})`}
    >
      {/* Image preview */}
      {imageUrl ? (
        <img
          src={imageUrl}
          alt={file.name}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      ) : (
        /* Icon preview for non-images */
        <div className="w-full h-full flex flex-col items-center justify-center p-1">
          <Icon className="w-6 h-6 text-muted-foreground mb-0.5" aria-hidden="true" />
          <span className="text-[8px] text-muted-foreground text-center truncate w-full px-1">
            {file.name.split('.').pop()?.toUpperCase()}
          </span>
        </div>
      )}

      {/* Remove button */}
      {!disabled && (
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRemove(index);
          }}
          className={cn(
            'absolute -top-1 -right-1',
            'w-5 h-5 rounded-full',
            'bg-destructive text-destructive-foreground',
            'flex items-center justify-center',
            'opacity-0 group-hover:opacity-100',
            'transition-opacity duration-200',
            'focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring'
          )}
          aria-label={`Remove ${file.name}`}
          type="button"
        >
          <X className="w-3 h-3" />
        </button>
      )}

      {/* File name tooltip on hover */}
      <div
        className={cn(
          'absolute bottom-0 left-0 right-0',
          'bg-black/70 text-white text-[9px] px-1 py-0.5',
          'truncate opacity-0 group-hover:opacity-100',
          'transition-opacity duration-200'
        )}
      >
        {file.name}
      </div>
    </div>
  );
}

/**
 * FilePreview - displays attached files with remove capability
 */
export function FilePreview({ files, onRemove, disabled = false }: FilePreviewProps) {
  if (files.length === 0) return null;

  return (
    <div
      className={cn(
        'flex flex-wrap gap-2 p-2',
        'border-t border-border bg-muted/30'
      )}
      role="list"
      aria-label={`${files.length} file${files.length !== 1 ? 's' : ''} attached`}
    >
      {files.map((file, index) => (
        <SingleFilePreview
          key={`${file.name}-${file.size}-${index}`}
          file={file}
          index={index}
          onRemove={onRemove}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

export default FilePreview;
