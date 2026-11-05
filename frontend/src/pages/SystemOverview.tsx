import {useQuery} from '@tanstack/react-query';
import {Activity,ArrowUpRight,Building2,ShieldCheck,Store,Tags,Users,UsersRound} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {User} from '../types';

const links=[
  {to:'/users',title:'User access',description:'Create accounts, verify registrations, and manage user access.',icon:Users},
  {to:'/departments',title:'Departments',description:'Maintain the departments available for procurement projects.',icon:Building2},
  {to:'/vendors',title:'Verified vendors',description:'Review vendor records and the suppliers available to projects.',icon:Store},
  {to:'/categories',title:'Vendor categories',description:'Maintain category labels used to organize verified suppliers.',icon:Tags},
  {to:'/committees',title:'Committees',description:'Review project committees and stage member assignments.',icon:UsersRound},
  {to:'/admins',title:'Administrator accounts',description:'Manage administrator roles and access.',icon:ShieldCheck},
  {to:'/audit',title:'Audit history',description:'Review recorded administrative and procurement operations.',icon:Activity},
];

export default function SystemOverview({user}:{user:User}){
  const status=useQuery({queryKey:['system-overview-status'],queryFn:async()=>{const [summary,departments]=await Promise.all([api.get('/dashboard/summary/'),api.get('/departments/')]);return {summary:summary.data,departments:departments.data.results||[]}}});
  return <div className="content">
    <div className="heading"><div><h1>System overview</h1><div className="muted">Workspace health and administration shortcuts.</div></div><span className="status"><ShieldCheck size={13} style={{verticalAlign:'middle',marginRight:5}}/>Super Admin</span></div>
    <section className="system-health"><div className="system-health__icon"><Activity size={20}/></div><div><b>Workspace services</b><p>{status.isLoading?'Checking API and workspace data…':status.isError?'The API could not return workspace status. Check the backend connection.':'API connected · project and department data are available.'}</p></div><span className={`system-health__state ${status.isError?'is-error':status.isSuccess?'is-ok':''}`}>{status.isLoading?'Checking':status.isError?'Unavailable':'Connected'}</span></section>
    <div className="cards system-stats"><div className="card"><div className="card-label">Projects</div><div className="card-value">{status.data?.summary?.total_projects??'—'}</div></div><div className="card"><div className="card-label">Active workflow</div><div className="card-value">{status.data?.summary?.active_projects??'—'}</div></div><div className="card"><div className="card-label">Departments</div><div className="card-value">{status.data?.departments?.length??'—'}</div></div></div>
    <div className="heading system-section-heading"><div><h2>Administration</h2><div className="muted">Manage workspace records and review changes.</div></div></div>
    <div className="system-link-grid">{links.map(({to,title,description,icon:Icon})=><Link to={to} key={to} className="system-link-card"><span><Icon size={18}/></span><div><b>{title}</b><p>{description}</p></div><ArrowUpRight size={16}/></Link>)}</div>
    <p className="muted system-account">Signed in as {user.name} · {user.email}</p>
  </div>;
}
