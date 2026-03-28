import { Check } from "lucide-react";
import { Button } from "./ui/button";

interface SuggestedResponseProps {
  text: string;
  onClick: (text: string) => void;
}

export function SuggestedResponse({ text, onClick }: SuggestedResponseProps) {
  return (
    <Button
      variant="default"
      className="bg-[#3b7ba8] hover:bg-[#2f6a92] text-white rounded-full px-3 py-1 text-xs h-auto flex items-center gap-1.5"
      onClick={() => onClick(text)}
    >
      <Check className="size-3" />
      {text}
    </Button>
  );
}