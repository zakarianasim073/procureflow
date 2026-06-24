import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File, X } from 'lucide-react';

interface Props {
  label: string; accept: Record<string, string[]>;
  onFileSelected: (file: File) => void;
  selectedFile: File | null;
  onClear: () => void;
}

export default function FileUploader({ label, accept, onFileSelected, selectedFile, onClear }: Props) {
  const onDrop = useCallback((files: File[]) => {
    if (files.length > 0) onFileSelected(files[0]);
  }, [onFileSelected]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept, multiple: false,
  });

  if (selectedFile) {
    return (
      <div className="file-drop-zone active p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <File size={32} className="text-primary-500" />
            <div>
              <p className="font-medium text-gray-900 dark:text-white text-sm">{selectedFile.name}</p>
              <p className="text-xs text-gray-400">{(selectedFile.size / 1024).toFixed(1)} KB</p>
            </div>
          </div>
          <button onClick={onClear} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
            <X size={16} className="text-gray-400" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div {...getRootProps()} className={`file-drop-zone p-8 text-center cursor-pointer ${isDragActive ? 'active' : ''}`}>
      <input {...getInputProps()} />
      <Upload size={36} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
      <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">{label}</p>
      <p className="text-xs text-gray-400 mt-1">Drop file or click to browse</p>
      <p className="text-xs text-gray-300 mt-1">PDF, XLSX, XLS supported</p>
    </div>
  );
}
