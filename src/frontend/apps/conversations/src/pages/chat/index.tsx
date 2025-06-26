import type { ReactElement } from 'react';

import { Chat } from '@/features/chat/components/Chat';
import { MainLayout } from '@/layouts';
import { NextPageWithLayout } from '@/types/next';

const Page: NextPageWithLayout = () => {
  return <Chat initialConversationId={undefined} />;
};

Page.getLayout = function getLayout(page: ReactElement) {
  return <MainLayout backgroundColor="grey">{page}</MainLayout>;
};

export default Page;
