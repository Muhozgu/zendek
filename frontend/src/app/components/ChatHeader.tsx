import { Minus, ThumbsUp, ThumbsDown } from "lucide-react";
import { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";
import { Button } from "./ui/button";

export function ChatHeader() {
  return (
    <div>
      {/* Top bar */}
      <div className="bg-[#3b7ba8] text-white px-6 py-3 flex items-center justify-between">
        <h1 className="text-base font-medium">Live Support</h1>
        <Button variant="ghost" size="icon" className="text-white hover:bg-white/10 h-8 w-8">
          <Minus className="size-4" />
        </Button>
      </div>

      {/* Agent info bar */}
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Avatar className="size-10">
            <AvatarImage src="https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100&h=100&fit=crop" />
            <AvatarFallback>P</AvatarFallback>
          </Avatar>
          <div>
            <div className="text-sm font-medium text-gray-900">Phil</div>
            <div className="text-xs text-gray-500">Customer Support</div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 h-9 w-9">
            <ThumbsUp className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 h-9 w-9">
            <ThumbsDown className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}