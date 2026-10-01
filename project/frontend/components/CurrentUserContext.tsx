'use client';

import { createContext, useContext } from 'react';

type CurrentUser = { is_admin: boolean };

export const CurrentUserContext = createContext<CurrentUser | null>(null);
export function useCurrentUser() { return useContext(CurrentUserContext); }
