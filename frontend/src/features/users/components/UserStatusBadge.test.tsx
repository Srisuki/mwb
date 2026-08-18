import {render,screen} from '@testing-library/react';
import {describe,expect,it} from 'vitest';
import {UserStatusBadge} from './UserStatusBadge';

describe('UserStatusBadge',()=>{
  it('renders active and inactive account states',()=>{
    const {rerender}=render(<UserStatusBadge active/>);
    expect(screen.getByText('Active')).toBeTruthy();
    rerender(<UserStatusBadge active={false}/>);
    expect(screen.getByText('Inactive')).toBeTruthy();
  });
});
