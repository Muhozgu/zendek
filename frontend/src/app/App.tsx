import { useState } from "react";
import { ChatHeader } from "./components/ChatHeader";
import { ChatMessages } from "./components/ChatMessages";
import { ChatInput } from "./components/ChatInput";

export default function App() {
  const [messages, setMessages] = useState([
    { type: "system", text: "Chat started" },
    { type: "system", text: "Phil joined the chat" },
    {
      type: "agent",
      text: "Hello! Welcome to Customer Support Service!",
      sender: "Phil",
    },
    {
      type: "agent",
      text: "My name is Phil and I will be assisting you today.",
      sender: "Phil",
    },
    { type: "agent", text: "Hello, Ergson.", sender: "Phil" },
    { type: "agent", text: "How may I assist you?", sender: "Phil" },
    { type: "user", text: "hey" },
  ]);

  const [inputValue, setInputValue] = useState("");

  const handleSendMessage = (text: string) => {
    if (text.trim()) {
      setMessages([...messages, { type: "user", text: text.trim() }]);
      setInputValue("");
    }
  };

  return (
    <div className="size-full flex flex-col bg-white">
      <ChatHeader />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <ChatMessages messages={messages} />
        
        <div className="p-4 border-t bg-white">
          <ChatInput
            value={inputValue}
            onChange={setInputValue}
            onSend={handleSendMessage}
          />
        </div>
      </div>
    </div>
  );
}