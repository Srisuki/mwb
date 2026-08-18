import {api} from '../../../services/api';
import type {UserFilters} from '../types/user.types';

export const usersApi={
  list:(filters:UserFilters)=>api.users(filters),
  detail:api.user,
  roles:api.roles,
  permissions:api.permissions,
  clients:api.entities,
  create:api.createUser,
  update:api.updateUser,
  activate:api.activateUser,
  deactivate:api.deactivateUser,
};
