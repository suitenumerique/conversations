import { useMatch } from 'react-router';

/**
 * Id of the conversation in the URL, or undefined anywhere else.
 *
 * The header and the left panel render in the layout route, above the
 * `/chat/:id` match, where `useParams()` returns nothing: a route only exposes
 * the params it matched itself. `useMatch` tests the whole path, so it works
 * from any depth.
 */
export const useConversationRouteId = () => useMatch('/chat/:id')?.params.id;
