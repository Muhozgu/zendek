import { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";
import { motion } from "motion/react";

interface Message {
  type: "system" | "agent" | "user";
  text: string;
  sender?: string;
}

interface ChatMessagesProps {
  messages: Message[];
}

export function ChatMessages({ messages }: ChatMessagesProps) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 bg-gray-50">
      {messages.map((message, index) => {
        if (message.type === "system") {
          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="flex justify-center"
            >
              <div className="text-xs text-gray-400">
                {message.text}
              </div>
            </motion.div>
          );
        }

        if (message.type === "agent") {
          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4 }}
              className="flex items-start gap-2"
            >
              <Avatar className="size-8 mt-1">
                <AvatarImage src="https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100&h=100&fit=crop" />
                <AvatarFallback>P</AvatarFallback>
              </Avatar>
              <div className="flex flex-col gap-1">
                {index === 0 || messages[index - 1]?.sender !== message.sender ? (
                  <div className="text-xs text-gray-600">{message.sender}</div>
                ) : null}
                <div className="bg-gray-200 rounded-lg rounded-tl-sm px-3 py-2 max-w-md">
                  <p className="text-sm text-gray-800">{message.text}</p>
                </div>
              </div>
            </motion.div>
          );
        }

        if (message.type === "user") {
          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4 }}
              className="flex justify-end"
            >
              <div className="bg-[#3b7ba8] text-white rounded-lg rounded-tr-sm px-3 py-2 max-w-md">
                <p className="text-sm">{message.text}</p>
              </div>
            </motion.div>
          );
        }

        return null;
      })}
    </div>
  );
}