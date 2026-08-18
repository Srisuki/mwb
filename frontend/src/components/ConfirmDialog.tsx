import {useEffect,useRef} from "react";

export function ConfirmDialog({open,title,message,confirmLabel='Confirm',onConfirm,onCancel}:{open:boolean;title:string;message:string;confirmLabel?:string;onConfirm:()=>void;onCancel:()=>void}){
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const dialog=ref.current;if(!dialog)return;if(open&&!dialog.open)dialog.showModal();if(!open&&dialog.open)dialog.close()},[open]);
  return <dialog ref={ref} onCancel={event=>{event.preventDefault();onCancel()}}><h2>{title}</h2><p>{message}</p><div className="export-buttons"><button onClick={onCancel}>Cancel</button><button className="danger" onClick={onConfirm}>{confirmLabel}</button></div></dialog>;
}
