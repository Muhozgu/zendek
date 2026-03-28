import { Paperclip, Link as LinkIcon, MoreHorizontal, Send } from "lucide-react";
import { Button } from "./ui/button";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
}

export function ChatInput({ value, onChange, onSend }: ChatInputProps) {
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend(value);
    }
  };

  return (
    <div className="flex items-end gap-2">
      <div className="flex-1 relative">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type a message here..."
          className="w-full px-3 py-2 border border-gray-300 rounded text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 placeholder:text-gray-400"
          rows={1}
        />
      </div>
      
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 h-8 w-8">
          <Paperclip className="size-4" />
        </Button>
        <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 h-8 w-8">
          <LinkIcon className="size-4" />
        </Button>
        <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 h-8 w-8">
          <MoreHorizontal className="size-4" />
        </Button>
        <Button 
          onClick={() => onSend(value)}
          className="bg-[#3b7ba8] hover:bg-[#2f6a92] text-white h-8 w-8"
          size="icon"
        >
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  );
}