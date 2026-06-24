import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User, Languages } from 'lucide-react';
import { sendChat } from '../api/client';

interface Message { role: string; content: string; }

const welcomeMsg = {
  en: "Hello! I'm your BOQ analysis assistant. Ask me about zones, SOR rates, mismatch analysis, or BOQ uploads.",
  bn: "নমস্কার! আমি আপনার BOQ বিশ্লেষণ সহায়ক। জোন, SOR রেট, মিসম্যাচ বিশ্লেষণ বা BOQ আপলোড সম্পর্কে জিজ্ঞাসা করুন।"
};

export default function AIChat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: welcomeMsg.en }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lang, setLang] = useState<'en' | 'bn'>('en');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: 'user', content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setLoading(true);
    try {
      const res = await sendChat(
        newMessages.slice(-10).map(m => ({ role: m.role, content: m.content })),
        lang
      );
      setMessages(prev => [...prev, { role: 'assistant', content: res.content }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally { setLoading(false); }
  };

  const toggleLang = () => {
    setLang(prev => prev === 'en' ? 'bn' : 'en');
    setMessages([{ role: 'assistant', content: lang === 'en' ? welcomeMsg.bn : welcomeMsg.en }]);
  };

  return (
    <div className="p-6 max-w-4xl mx-auto h-[calc(100vh-6rem)] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Chat Assistant</h1>
        <button onClick={toggleLang}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
          <Languages size={16} /> {lang === 'en' ? 'বাংলা' : 'English'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4 mb-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex gap-3 max-w-[80%] ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`p-2 rounded-full ${msg.role === 'user' ? 'bg-primary-100 dark:bg-primary-900/30' : 'bg-gray-100 dark:bg-gray-700'} h-fit`}>
                {msg.role === 'user' ? <User size={16} className="text-primary-600" /> : <Bot size={16} className="text-gray-600" />}
              </div>
              <div className={`p-3 rounded-xl text-sm ${
                msg.role === 'user'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
              }`}>
                {msg.content}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 size={14} className="animate-spin" /> Thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2">
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={lang === 'en' ? "Ask about BOQ, SOR, zones..." : "BOQ, SOR, জোন সম্পর্কে জিজ্ঞাসা করুন..."}
          className="flex-1 px-4 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
        />
        <button onClick={handleSend} disabled={!input.trim() || loading}
          className="px-4 py-3 rounded-xl bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
