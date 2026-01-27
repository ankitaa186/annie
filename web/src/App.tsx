import { useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/layout';
import { ChatPage } from '@/pages/ChatPage';
import { ToastContainer } from '@/components/ui/toast';
import { useConversations } from '@/lib/hooks/useConversations';
import { useSession } from '@/lib/hooks/useSession';

function App() {
  // Initialize session on app mount
  const { initSession } = useSession();

  // Preload conversations on app mount
  const { fetchConversations } = useConversations();

  useEffect(() => {
    // Initialize session and fetch conversations when app loads
    initSession();
    fetchConversations();
  }, [initSession, fetchConversations]);

  return (
    <>
      <Layout>
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </Layout>
      <ToastContainer />
    </>
  );
}

export default App;
