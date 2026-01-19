import { type ReactElement, Suspense } from 'react';

import { Loader } from '@/components';
import { Chat } from '@/features/chat/components/Chat';
import { MainLayout } from '@/layouts';
import { NextPageWithLayout } from '@/types/next';

const Page: NextPageWithLayout = () => {
  return (
    <Suspense fallback={<Loader />}>
      <Chat initialConversationId={undefined} />
    </Suspense>
  );
};

Page.getLayout = function getLayout(page: ReactElement) {
  return <MainLayout>{page}</MainLayout>;
};

export default Page;
