import { Navigate } from 'react-router';

import { HOME_URL } from '@/features/auth';

const Page = () => {
  return <Navigate to={HOME_URL} replace />;
};

export default Page;
