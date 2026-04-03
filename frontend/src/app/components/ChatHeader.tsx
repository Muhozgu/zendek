import { X, Minimize2 } from 'lucide-react';

interface ChatHeaderProps {
  onClose?: () => void;
  onMinimize?: () => void;
}

export function ChatHeader({ onClose, onMinimize }: ChatHeaderProps) {
  return (
    <header className="sticky top-0 z-10 bg-[#1F3A5F] px-4 py-4 md:px-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-white text-lg font-semibold">Live Chat</h1>
          <p className="hidden md:block text-white/80 text-sm mt-0.5">Hyatt Support</p>
        </div>
        <div className="hidden md:flex items-center gap-2">
          {onMinimize && (
            <button
              onClick={onMinimize}
              className="text-white/80 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-colors"
              aria-label="Minimize chat"
            >
              <Minimize2 className="w-5 h-5" />
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="text-white/80 hover:text-white p-2 rounded-lg hover:bg-white/10 transition-colors"
              aria-label="Close chat"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
