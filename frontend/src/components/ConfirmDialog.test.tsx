import {fireEvent,render,screen} from '@testing-library/react';
import {beforeAll,describe,expect,it,vi} from 'vitest';
import {ConfirmDialog} from './ConfirmDialog';

beforeAll(()=>{
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')};
});

describe('ConfirmDialog',()=>{
  it('requires an explicit confirmation action',()=>{
    const confirm=vi.fn(),cancel=vi.fn();
    render(<ConfirmDialog open title="Archive document?" message="Evidence remains recoverable." onConfirm={confirm} onCancel={cancel}/>);
    expect(screen.getByRole('dialog').hasAttribute('open')).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(confirm).toHaveBeenCalledOnce();
    expect(cancel).not.toHaveBeenCalled();
  });
});
