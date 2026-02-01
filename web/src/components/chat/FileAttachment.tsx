import { memo, useState, useCallback } from 'react';
import {
  FileText,
  FileSpreadsheet,
  File,
  Image as ImageIcon,
  Download,
  X,
  Maximize2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { FileAttachment as FileAttachmentType } from '@/types';
import { formatFileSize, isImageFile, getFileCategory } from '@/types';

interface FileAttachmentProps {
  file: FileAttachmentType;
  className?: string;
}

/**
 * FileAttachment - Displays file attachments in messages
 *
 * Features:
 * - Images displayed inline with click-to-expand
 * - Documents shown as file cards with icon, name, size
 * - Type-specific icons for documents, spreadsheets
 */
export const FileAttachment = memo(function FileAttachment({
  file,
  className,
}: FileAttachmentProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const isImage = isImageFile(file.mime_type) && !imageError;
  const category = getFileCategory(file.mime_type);

  const handleImageClick = useCallback(() => {
    setIsExpanded(true);
  }, []);

  const handleCloseExpanded = useCallback(() => {
    setIsExpanded(false);
  }, []);

  const handleImageError = useCallback(() => {
    setImageError(true);
  }, []);

  // Get appropriate icon for file type
  const getFileIcon = () => {
    switch (category) {
      case 'document':
        return <FileText className="h-8 w-8 text-blue-500" />;
      case 'spreadsheet':
        return <FileSpreadsheet className="h-8 w-8 text-green-500" />;
      case 'image':
        return <ImageIcon className="h-8 w-8 text-purple-500" />;
      default:
        return <File className="h-8 w-8 text-muted-foreground" />;
    }
  };

  // Render image with click-to-expand
  if (isImage && file.url) {
    return (
      <>
        {/* Inline image */}
        <div className={cn('group relative mt-2 inline-block', className)}>
          <button
            onClick={handleImageClick}
            className="relative block overflow-hidden rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            aria-label={`View ${file.filename} full size`}
          >
            <img
              src={file.url}
              alt={file.filename}
              className="max-h-64 max-w-full rounded-lg object-contain"
              loading="lazy"
              onError={handleImageError}
            />
            <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover:bg-black/20 group-hover:opacity-100">
              <Maximize2 className="h-8 w-8 text-white drop-shadow-lg" />
            </div>
          </button>
          <div className="mt-1 text-xs text-muted-foreground">
            {file.filename} ({formatFileSize(file.size_bytes)})
          </div>
        </div>

        {/* Expanded modal */}
        {isExpanded && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
            onClick={handleCloseExpanded}
            role="dialog"
            aria-modal="true"
            aria-label={`Expanded view of ${file.filename}`}
          >
            <button
              onClick={handleCloseExpanded}
              className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
              aria-label="Close expanded view"
            >
              <X className="h-6 w-6" />
            </button>
            <img
              src={file.url}
              alt={file.filename}
              className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
      </>
    );
  }

  // Render document as card
  return (
    <Card
      className={cn(
        'mt-2 flex items-center gap-3 p-3 transition-colors hover:bg-muted/50',
        className
      )}
    >
      <div className="flex-shrink-0">{getFileIcon()}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium text-sm" title={file.filename}>
          {file.filename}
        </div>
        <div className="text-xs text-muted-foreground">
          {formatFileSize(file.size_bytes)}
        </div>
      </div>
      {file.url && (
        <Button
          variant="ghost"
          size="sm"
          className="flex-shrink-0"
          asChild
        >
          <a
            href={file.url}
            download={file.filename}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Download ${file.filename}`}
          >
            <Download className="h-4 w-4" />
          </a>
        </Button>
      )}
    </Card>
  );
});

export default FileAttachment;
