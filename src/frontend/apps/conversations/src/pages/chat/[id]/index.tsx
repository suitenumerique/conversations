import { useRouter } from 'next/router';
import type { ReactElement } from 'react';

import { Chat } from '@/features/chat/components/Chat';
import { MainLayout } from '@/layouts';
import { NextPageWithLayout } from '@/types/next';

const Page: NextPageWithLayout = () => {
  const router = useRouter();
  const { id } = router.query;

  return <Chat initialConversationId={id as string} />;
};

Page.getLayout = function getLayout(page: ReactElement) {
  return <MainLayout backgroundColor="grey">{page}</MainLayout>;
};

export default Page;
