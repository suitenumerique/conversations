import { Suspense } from 'react';
import { useParams } from 'react-router';

import { Loader } from '@/components';
import { Chat } from '@/features/chat/components/Chat';

const Page = () => {
  const { id } = useParams();

  return (
    <Suspense fallback={<Loader />}>
      <Chat initialConversationId={id} />
    </Suspense>
  );
};

export default Page;
