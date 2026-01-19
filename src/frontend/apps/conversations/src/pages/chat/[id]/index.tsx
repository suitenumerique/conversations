import { useRouter } from 'next/router';
import { type ReactElement, Suspense } from 'react';

import { Loader } from '@/components';
import { Chat } from '@/features/chat/components/Chat';
import { MainLayout } from '@/layouts';
import { NextPageWithLayout } from '@/types/next';

const Page: NextPageWithLayout = () => {
  const router = useRouter();
  const { id } = router.query;

  return (
    <Suspense fallback={<Loader />}>
      <Chat initialConversationId={id as string} />
    </Suspense>
  );
};

Page.getLayout = function getLayout(page: ReactElement) {
  return <MainLayout>{page}</MainLayout>;
};

export default Page;
