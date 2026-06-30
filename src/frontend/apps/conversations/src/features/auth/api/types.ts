/**
 * Represents user retrieved from the API.
 * @interface User
 * @property {string} id - The id of the user.
 * @property {string} email - The email of the user.
 * @property {string} name - The name of the user.
 * @property {string} language - The language of the user. e.g. 'en-us', 'fr-fr', 'de-de'.
 * @property {string} sub - The identity provider sub.
 */
export interface User {
  id: string;
  email: string | null;
  full_name: string | null;
  short_name: string | null;
  language?: string;
  allow_smart_web_search: boolean;
  allow_conversation_analytics: boolean;
  sub?: string;
}
