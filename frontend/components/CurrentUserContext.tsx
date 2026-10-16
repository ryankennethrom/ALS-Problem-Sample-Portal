'use client';

import { createContext, useContext } from 'react';

type CurrentUser = { is_admin: boolean; role: string };

export const CurrentUserContext = createContext<CurrentUser | null>(null);
export function useCurrentUser() { return useContext(CurrentUserContext); }
