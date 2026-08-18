import {useCallback,useEffect,useState} from 'react';
import type {User} from '../../../types';
import {usersApi} from '../services/usersApi';
import type {UserFilters} from '../types/user.types';
export function useUsers(filters:UserFilters){const [users,setUsers]=useState<User[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');const reload=useCallback(()=>{setLoading(true);setError('');return usersApi.list(filters).then(setUsers).catch(reason=>setError(reason.message)).finally(()=>setLoading(false))},[filters.search,filters.role,filters.client,filters.status,filters.page,filters.page_size]);useEffect(()=>{reload()},[reload]);return {users,loading,error,reload}}
