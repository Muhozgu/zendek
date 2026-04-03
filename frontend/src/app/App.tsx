import { useState, useRef, useEffect } from 'react';
import { ChatHeader } from './components/ChatHeader';
import { MessageBubble } from './components/MessageBubble';
import { TypingIndicator } from './components/TypingIndicator';
import { ChatInput } from './components/ChatInput';
import { StatusIndicator } from './components/StatusIndicator';

interface Message {
  id: number;
  type: 'system' | 'user' | 'agent';
  content: string;
  timestamp?: string;
  showAvatar?: boolean;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      type: 'system',
      content: 'Chat Started 01:07 PM',
      showAvatar: true,
    },
    {
      id: 2,
      type: 'system',
      content: 'Your personal information is protected and will not be shared with third parties without your consent.',
      timestamp: '01:07 PM',
      showAvatar: false,
    },
    {
      id: 3,
      type: 'system',
      content: 'Waiting for Agent...',
      showAvatar: false,
    },
    {
      id: 4,
      type: 'system',
      content: 'A colleague will be with you momentarily.',
      showAvatar: false,
    },
    {
      id: 5,
      type: 'system',
      content: 'All colleagues are currently assisting other guests. Your patience is appreciated.',
      timestamp: '01:08 PM',
      showAvatar: false,
    },
    {
      id: 6,
      type: 'user',
      content: 'Found the reservation number!',
      timestamp: 'Just now',
    },
  ]);

  const [isTyping, setIsTyping] = useState(true);
  const [status] = useState<'online' | 'connecting' | 'offline'>('online');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSendMessage = (content: string) => {
    const newMessage: Message = {
      id: messages.length + 1,
      type: 'user',
      content,
      timestamp: 'Just now',
    };
    setMessages([...messages, newMessage]);

    // Simulate agent typing after user sends a message
    setTimeout(() => {
      setIsTyping(true);
      setTimeout(() => {
        setIsTyping(false);
        const agentMessage: Message = {
          id: messages.length + 2,
          type: 'agent',
          content: 'Thank you for that information! Let me check that for you.',
          timestamp: new Date().toLocaleTimeString('en-US', { 
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
          }),
          showAvatar: true,
        };
        setMessages(prev => [...prev, agentMessage]);
      }, 2000);
    }, 500);
  };

  return (
    <div className="min-h-screen bg-gray-100 md:bg-gray-200 flex items-center justify-center p-0 md:p-4 lg:p-8">
      {/* Chat Container */}
      <div className="w-full h-screen md:h-[90vh] md:max-h-[800px] max-w-[480px] lg:max-w-[600px] bg-white md:rounded-2xl md:shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <ChatHeader 
          onClose={() => console.log('Close chat')}
          onMinimize={() => console.log('Minimize chat')}
        />

        {/* Status Indicator */}
        <StatusIndicator status={status} />

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto bg-[#F7F7F7] px-4 py-6 md:px-6">
          <div className="space-y-0">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                type={message.type}
                content={message.content}
                timestamp={message.timestamp}
                showAvatar={message.showAvatar}
              />
            ))}
            {isTyping && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <ChatInput onSendMessage={handleSendMessage} />
      </div>
    </div>
  );
}

export default App;
