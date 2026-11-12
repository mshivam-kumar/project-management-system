import {useState} from 'react';
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {Check,Plus,Search,Shield,Trash2,UserRoundX,X} from 'lucide-react';
import {api} from '../services/api';
import type {User} from '../types';

type Kind='users'|'admins'|'departments'|'vendors'|'audit'|'notifications';
const titleByKind:Record<Kind,string>={users:'Employee Management',admins:'Admin Management',departments:'Departments',vendors:'Vendor Management',audit:'Audit Logs',notifications:'Notifications'};
export default function Management({kind,user}:{kind:Kind;user:User}){
 const qc=useQueryClient();const [search,setSearch]=useState('');const [filter,setFilter]=useState('');const [showForm,setShowForm]=useState(false);
 const path=kind==='admins'?'/users/':`/${kind==='audit'?'audit-logs':kind}/`;
 const query=useQuery({queryKey:[kind,search,filter,user.id],queryFn:async()=>{const params:any={search};if(filter)params[kind==='users'?'verification_status':kind==='vendors'?'verification_status':'is_active']=filter;if(kind==='admins')params['roles__name']='ADMIN';const r=await api.get(path,{params});return r.data.results||r.data}});
 const action=useMutation({mutationFn:({url,method='post',data}:any)=>api.request({url,method,data}),onSuccess:()=>{qc.invalidateQueries({queryKey:[kind]});qc.invalidateQueries({queryKey:['dashboard-summary']})}});
 const create=useMutation({mutationFn:(data:any)=>api.post(path,data),onSuccess:()=>{qc.invalidateQueries({queryKey:[kind]});qc.invalidateQueries({queryKey:['dashboard-summary']});setShowForm(false)}});
 const canCreate=kind==='departments'||kind==='vendors'||kind==='users'||kind==='admins';
 const rows=query.data||[];
 return <div className="content"><div className="heading"><div><h1>{titleByKind[kind]}</h1><div className="muted">Manage records, review requests, and inspect history.</div></div>{canCreate&&<button className="button primary" onClick={()=>setShowForm(v=>!v)}><Plus size={15} style={{verticalAlign:'middle',marginRight:6}}/>{kind==='users'?'Add employee':kind==='admins'?'Add user':kind==='vendors'?'Add vendor':'Add department'}</button>}</div>
 {kind==='notifications'?<NotificationList userId={user.id}/>:kind==='audit'?<AuditTable query={query}/>:<>
 {showForm&&<RecordForm kind={kind} isSuperAdmin={user.roles?.includes('SUPER_ADMIN')} busy={create.isPending} error={create.isError} onCancel={()=>setShowForm(false)} onSave={(data:any)=>create.mutate(data)}/>}
 <div className="panel"><div className="panel-head"><b>{kind==='admins'?'Administrator accounts':titleByKind[kind]}</b><div className="toolbar"><div style={{position:'relative'}}><Search size={15} style={{position:'absolute',left:10,top:11,color:'#8290a1'}}/><input style={{paddingLeft:32}} placeholder="Search…" value={search} onChange={e=>setSearch(e.target.value)}/></div>{(kind==='users'||kind==='vendors')&&<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All verification</option>{['PENDING','VERIFIED','REJECTED'].map(s=><option key={s}>{s}</option>)}</select>}</div></div>
 {query.isLoading?<div className="empty">Loading…</div>:query.isError?<div className="empty">Could not load records.</div>:kind==='departments'?<DepartmentTable rows={rows} mutate={action.mutate}/>:kind==='vendors'?<VendorTable rows={rows} mutate={action.mutate}/>:<UserTable rows={rows} kind={kind} canAssign={user.roles?.includes('SUPER_ADMIN')} mutate={action.mutate}/>}
 {action.isError&&<div style={{padding:14,color:'#b42318',fontSize:13}}>That action failed. Check permissions and try again.</div>}
 </div></>}
 </div>
}
function UserTable({rows,kind,canAssign,mutate}:{rows:any[];kind:Kind;canAssign:boolean|undefined;mutate:(x:any)=>void}){return <table><thead><tr><th>EMPLOYEE</th><th>EMPLOYEE ID</th><th>EMAIL</th><th>DEPARTMENT</th><th>ROLE</th><th>VERIFICATION</th><th>ACCOUNT</th><th>ACTIONS</th></tr></thead><tbody>{rows.map(u=><tr key={u.id}><td>{u.name}{u.designation&&<div className="muted">{u.designation}</div>}</td><td>{u.employee_id||'—'}</td><td>{u.email}</td><td>{u.department_name||'—'}</td><td>{(u.roles||[]).map((role:string)=>role==='IA_WING'?'IA Wing':role).join(', ')||'USER'}</td><td><span className="status">{u.verification_status}</span></td><td>{u.is_active?'Active':'Inactive'}</td><td style={{whiteSpace:'nowrap'}}>{u.verification_status==='PENDING'&&<><button className="icon-button" title="Verify account" onClick={()=>mutate({url:`/users/${u.id}/verify/`,data:{}})}><Check size={15}/></button> <button className="icon-button" title="Reject registration" onClick={()=>mutate({url:`/users/${u.id}/reject/`,data:{}})}><X size={15}/></button></>}{kind==='admins'&&canAssign&&<button className="icon-button" title="Assign ADMIN role" onClick={()=>mutate({url:`/users/${u.id}/assign_role/`,data:{role:'ADMIN'}})}><Shield size={15}/></button>}{u.is_active&&<button className="icon-button" title="Deactivate" onClick={()=>mutate({url:`/users/${u.id}/deactivate/`,data:{}})}><UserRoundX size={15}/></button>}</td></tr>)}</tbody></table>}
function DepartmentTable({rows,mutate}:{rows:any[];mutate:(x:any)=>void}){return <table><thead><tr><th>NAME</th><th>CODE</th><th>DESCRIPTION</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{rows.map(d=><tr key={d.id}><td>{d.department_name}</td><td>{d.department_code}</td><td>{d.description||'—'}</td><td>{d.is_active?'Active':'Inactive'}</td><td><button className="icon-button" onClick={()=>mutate({url:`/departments/${d.id}/`,method:'patch',data:{is_active:!d.is_active}})}>{d.is_active?'Deactivate':'Activate'}</button></td></tr>)}</tbody></table>}
function VendorTable({rows,mutate}:{rows:any[];mutate:(x:any)=>void}) {
 const [editingId,setEditingId]=useState<string|null>(null);
 const [productsServices,setProductsServices]=useState('');
 return <table><thead><tr><th>VENDOR</th><th>PRODUCTS / SERVICES</th><th>REGISTRATION / GSTIN</th><th>CONTACT</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{rows.map(v=><tr key={v.id}>
  <td><b>{v.vendor_name}</b><div className="muted">{v.address}</div></td>
  <td>{editingId===v.id?<form onSubmit={e=>{e.preventDefault();mutate({url:`/vendors/${v.id}/`,method:'patch',data:{products_services:productsServices}});setEditingId(null)}}><textarea value={productsServices} onChange={e=>setProductsServices(e.target.value)} aria-label={`Products and services offered by ${v.vendor_name}`} /><button className="icon-button">Save</button></form>:<><div>{v.products_services||'—'}</div><div className="muted">{v.category_names?.join(', ')}</div><button className="icon-button" onClick={()=>{setEditingId(v.id);setProductsServices(v.products_services||'')}}>Edit offerings</button></>}</td>
  <td>{v.registration_number||'—'} / {v.gstin||'—'}</td><td>{v.email}<br/>{v.phone}</td><td><span className="status">{v.verification_status}</span></td>
  <td style={{whiteSpace:'nowrap'}}>{v.verification_status!=='VERIFIED'&&<button className="icon-button" onClick={()=>mutate({url:`/vendors/${v.id}/verify/`,data:{}})}>Verify</button>} <button className="icon-button" onClick={()=>mutate({url:`/vendors/${v.id}/reject/`,data:{}})}>Reject</button> <label className="icon-button" style={{cursor:'pointer'}}>PDF<input hidden type="file" accept="application/pdf,.pdf" onChange={e=>{const file=e.target.files?.[0];if(file){const data=new FormData();data.append('file',file);mutate({url:`/vendors/${v.id}/documents/`,data})}}}/></label></td>
 </tr>)}</tbody></table>;
}
function AuditTable({query}:{query:any}){const rows=query.data||[];return query.isLoading?<div className="empty">Loading audit history…</div>:query.isError?<div className="empty">Could not load audit history.</div>:<table><thead><tr><th>WHEN</th><th>ACTOR</th><th>OPERATION</th><th>ENTITY</th><th>ID</th></tr></thead><tbody>{rows.map((r:any)=><tr key={r.id}><td>{new Date(r.created_at).toLocaleString()}</td><td>{r.user||'System'}</td><td>{r.operation}</td><td>{r.entity_type}</td><td>{r.entity_id}</td></tr>)}</tbody></table>}
function NotificationList({ userId }: { userId: string }) {
 const qc = useQueryClient();
 const q = useQuery({
  queryKey: ['notifications', userId],
  queryFn: async () => {
   const response = await api.get('/notifications/');
   return response.data.results || [];
  },
 });
 const read = useMutation({
  mutationFn: (id: string) => api.patch(`/notifications/${id}/read/`),
  onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
 });
 if (q.isLoading) return <div className="empty">Loading notifications…</div>;
 if (q.isError) return <div className="empty">Could not load notifications.</div>;
 return (
  <div className="panel">
   <table>
    <thead><tr><th>NOTIFICATION</th><th>DATE</th><th>STATUS</th><th>ACTION</th></tr></thead>
    <tbody>{q.data.map((notification: any) => {
     const projectUrl = notification.project ? `/projects/${notification.project}#project-workflow` : null;
     const markRead = () => {
      if (!notification.is_read) read.mutate(notification.id);
     };
     return (
      <tr key={notification.id}>
       <td>
        {projectUrl
         ? <Link to={projectUrl} onClick={markRead}><b>{notification.title}</b></Link>
         : <b>{notification.title}</b>}
        <div className="muted">{notification.message}</div>
       </td>
       <td>{new Date(notification.created_at).toLocaleString()}</td>
       <td>{notification.is_read ? 'Read' : 'Unread'}</td>
       <td>
        {projectUrl && <Link className="button project-details-button" to={projectUrl} onClick={markRead}>Open project</Link>}
        {!notification.is_read && <button className="icon-button" onClick={markRead}>Mark read</button>}
       </td>
      </tr>
     );
    })}</tbody>
   </table>
   {!q.data.length && <div className="empty">No notifications.</div>}
  </div>
 );
}
function RecordForm({kind,isSuperAdmin,busy,error,onCancel,onSave}:{kind:Kind;isSuperAdmin:boolean|undefined;busy:boolean;error:boolean;onCancel:()=>void;onSave:(data:any)=>void}) {
 const [form,setForm]=useState<any>({});
 const inputStyle={display:'block',width:'100%',padding:10,border:'1px solid #dfe5ec',borderRadius:8,marginTop:5};
 const field=(key:string,label:string,type='text',required=true)=><label style={{display:'block',marginBottom:12}}><span className="muted">{label}</span>{type==='textarea'?<textarea required={required} value={form[key]||''} onChange={e=>setForm({...form,[key]:e.target.value})} style={inputStyle}/>:<input required={required} type={type} value={form[key]||''} onChange={e=>setForm({...form,[key]:e.target.value})} style={inputStyle}/>}</label>;
 const departmentOptions=useQuery({queryKey:['departments'],enabled:kind==='users'||kind==='admins',queryFn:async()=>{const r=await api.get('/departments/');return r.data.results||[]}});
 return <div className="card" style={{marginBottom:16}}>
  <div className="heading"><b>Create {kind==='vendors'?'vendor':kind==='departments'?'department':kind==='users'?'employee':'user'}</b><button className="icon-button" onClick={onCancel}><X size={15}/></button></div>
  <form onSubmit={e=>{e.preventDefault();onSave(form)}} style={{maxWidth:650}}>
   {kind==='departments'?<>{field('department_name','Department name')}{field('department_code','Code')}{field('description','Description','textarea',false)}</>:kind==='vendors'?<>{field('vendor_name','Vendor name')}{field('products_services','Products / services offered','textarea',false)}{field('registration_number','Registration number','text',false)}{field('gstin','GSTIN','text',false)}{field('email','Email','email',false)}{field('phone','Phone','text',false)}{field('address','Address','textarea',false)}</>:<>{field('name','Full name')}{field('employee_id','Employee ID')}{field('email','Email','email')}{field('password','Temporary password','password')}<label style={{display:'block',marginBottom:12}}><span className="muted">Department</span><select value={form.department||''} onChange={e=>setForm({...form,department:e.target.value})} style={inputStyle}><option value="">Choose department</option>{departmentOptions.data?.map((d:any)=><option key={d.id} value={d.id}>{d.department_name}</option>)}</select></label>{field('designation','Designation','text',false)}<label className="muted">Role <select value={form.role||'USER'} onChange={e=>setForm({...form,role:e.target.value})}><option value="USER">USER</option><option value="AS">AS</option><option value="HQ">HQ</option><option value="SS">SS</option><option value="DGS">DGS</option><option value="IA_WING">IA Wing</option>{isSuperAdmin&&<option value="ADMIN">ADMIN</option>}</select></label></>}
   {error&&<p style={{color:'#b42318'}}>Could not save. Check required fields and your permissions.</p>}
   <div style={{marginTop:14}}><button disabled={busy} className="button primary">{busy?'Saving…':'Save'}</button> <button type="button" onClick={onCancel} className="icon-button">Cancel</button></div>
  </form>
 </div>;
}
