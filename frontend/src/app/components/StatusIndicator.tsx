import { motion } from 'motion/react';

interface StatusIndicatorProps {
  status: 'online' | 'connecting' | 'offline';
}

export function StatusIndicator({ status }: StatusIndicatorProps) {
  const statusConfig = {
    online: {
      color: 'bg-green-500',
      text: 'Online',
      animate: false,
    },
    connecting: {
      color: 'bg-yellow-500',
      text: 'Connecting...',
      animate: true,
    },
    offline: {
      color: 'bg-gray-400',
      text: 'Offline',
      animate: false,
    },
  };

  const config = statusConfig[status];

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-white/90 backdrop-blur-sm">
      <div className="relative">
        {config.animate ? (
          <motion.div
            className={`w-2 h-2 ${config.color} rounded-full`}
            animate={{
              opacity: [1, 0.3, 1],
            }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
            }}
          />
        ) : (
          <div className={`w-2 h-2 ${config.color} rounded-full`} />
        )}
      </div>
      <span className="text-xs text-gray-600">{config.text}</span>
    </div>
  );
}
