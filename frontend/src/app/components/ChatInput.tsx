import { useState } from 'react';
import { Send, Type, Volume2 } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSendMessage, disabled = false }: ChatInputProps) {
  const [message, setMessage] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  return (
    <div className="sticky bottom-0 bg-white border-t border-gray-200 px-4 py-4 md:px-6">
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          className="hidden md:flex shrink-0 w-9 h-9 items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          aria-label="Text size"
        >
          <Type className="w-5 h-5" />
        </button>
        <button
          type="button"
          className="hidden md:flex shrink-0 w-9 h-9 items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          aria-label="Audio"
        >
          <Volume2 className="w-5 h-5" />
        </button>
        <div className="flex-1 relative">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type Something..."
            disabled={disabled}
            className="w-full px-4 py-3 bg-gray-100 rounded-full border-none focus:outline-none focus:ring-2 focus:ring-[#4A90E2] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
        <button
          type="submit"
          disabled={!message.trim() || disabled}
          className="shrink-0 w-11 h-11 bg-[#4A90E2] hover:bg-[#3A7BC8] disabled:bg-gray-300 disabled:cursor-not-allowed rounded-full flex items-center justify-center transition-colors shadow-md"
          aria-label="Send message"
        >
          <Send className="w-5 h-5 text-white" />
        </button>
      </form>
    </div>
  );
}
