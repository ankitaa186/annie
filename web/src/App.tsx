import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/layout';
import { ChatPage } from '@/pages/ChatPage';
import { ToastContainer } from '@/components/ui/toast';

function App() {
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
