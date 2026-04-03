import { MessageCircle } from 'lucide-react';

export type MessageType = 'system' | 'user' | 'agent';

interface MessageBubbleProps {
  type: MessageType;
  content: string;
  timestamp?: string;
  showAvatar?: boolean;
}

export function MessageBubble({ type, content, timestamp, showAvatar = true }: MessageBubbleProps) {
  if (type === 'system') {
    return (
      <div className="flex gap-3 mb-4">
        {showAvatar && (
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center">
            <MessageCircle className="w-4 h-4 text-gray-600" />
          </div>
        )}
        <div className={showAvatar ? '' : 'ml-11'}>
          <div className="bg-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[280px] md:max-w-sm">
            <p className="text-gray-700 text-sm leading-relaxed">{content}</p>
          </div>
          {timestamp && (
            <p className="text-xs text-gray-500 mt-1 ml-1">{timestamp}</p>
          )}
        </div>
      </div>
    );
  }

  if (type === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div>
          <div className="bg-[#4A90E2] rounded-2xl rounded-tr-sm px-4 py-3 max-w-[280px] md:max-w-sm">
            <p className="text-white text-sm leading-relaxed">{content}</p>
          </div>
          {timestamp && (
            <p className="text-xs text-gray-500 mt-1 mr-1 text-right">{timestamp}</p>
          )}
        </div>
      </div>
    );
  }

  // Agent type (similar to system but could have different styling)
  return (
    <div className="flex gap-3 mb-4">
      {showAvatar && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#1F3A5F] flex items-center justify-center">
          <MessageCircle className="w-4 h-4 text-white" />
        </div>
      )}
      <div className={showAvatar ? '' : 'ml-11'}>
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 max-w-[280px] md:max-w-sm shadow-sm border border-gray-100">
          <p className="text-gray-700 text-sm leading-relaxed">{content}</p>
        </div>
        {timestamp && (
          <p className="text-xs text-gray-500 mt-1 ml-1">{timestamp}</p>
        )}
      </div>
    </div>
  );
}
