import { create } from 'zustand';
import { Role } from '../lib/types';

interface RoleState {
  activeRole: Role;
  setRole: (role: Role) => void;
}

export const useRoleStore = create<RoleState>((set) => ({
  activeRole: 'Admin',
  setRole: (activeRole) => set({ activeRole }),
}));
