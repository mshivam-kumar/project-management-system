import {useQuery} from '@tanstack/react-query';
import {ArrowRight,ClipboardCheck,MessageCircleQuestion,RefreshCw} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {api} from '../services/api';

type Task={id:string;task_type:'WORKFLOW_ACTION'|'QUERY_REPLY';project_id:string;project_code:string;project_title:string;current_status:string;title:string;detail?:string;created_at:string};
const stageNames:Record<string,string>={DRAFT:'Requirement',TSC_APPROVAL:'TSC approval',BOARD_FORMATION:'Board formation',TSC_REPORT_AS_IA:'TSC report · AS (IA)',AS_IA_APPROVAL:'AS (IA) approval','DG_SS_APPROVAL':'DG/SS approval',HQ_REVIEW:'HQ review',CS_SR_REVIEW:'CS (SR) review',DRAFT_TENDER_IA:'Draft tender · IA wing',TENDER_ISSUED:'Tender issued',VENDOR_RESPONSE:'Vendor responses',TECH_BID_BOARD:'Technical bid board',TEC_FORMATION:'TEC formation',TEC_REPORT:'TEC report',PRICE_BID_OPEN:'Price bid opening',TAC_REVIEW:'TAC review',IFD_CFA_APPROVAL:'IFD/CFA approval',APPROVED:'Approved',RETURNED:'Returned',REJECTED:'Rejected',CANCELLED:'Cancelled'};

export default function MyTasks(){
  const navigate=useNavigate();
  const tasks=useQuery({queryKey:['my-tasks'],queryFn:async()=> (await api.get('/projects/my-tasks/')).data as Task[]});
  const openProject=(task:Task)=>navigate('/projects',{state:{openProjectId:task.project_id}});
  const pending=tasks.data||[];
  return <div className="content">
    <div className="heading"><div><h1>My Tasks</h1><div className="muted">Work assigned to your current stage and open project queries.</div></div><button className="icon-button" onClick={()=>tasks.refetch()} disabled={tasks.isFetching}><RefreshCw size={15} style={{verticalAlign:'middle',marginRight:6}}/>{tasks.isFetching?'Refreshing…':'Refresh'}</button></div>
    <div className="task-summary"><div><b>{pending.length}</b><span>Open task{pending.length===1?'':'s'}</span></div><p>Tasks appear here when your account can act on a project’s current stage or reply to an open query.</p></div>
    {tasks.isLoading?<div className="empty">Loading your tasks…</div>:tasks.isError?<div className="empty"><p>Could not load tasks.</p><button className="button" onClick={()=>tasks.refetch()}>Try again</button></div>:pending.length===0?<div className="empty task-empty"><ClipboardCheck size={26}/><h3>You’re all caught up</h3><p>No stage actions or open queries are assigned to you right now.</p></div>:<div className="task-list">{pending.map(task=>{
      const queryTask=task.task_type==='QUERY_REPLY';
      return <article className="task-card" key={task.id}>
        <div className="task-card__icon" data-kind={queryTask?'query':'stage'}>{queryTask?<MessageCircleQuestion size={18}/>:<ClipboardCheck size={18}/>}</div>
        <div className="task-card__body"><div className="task-card__top"><span className={`activity-badge activity-badge--${queryTask?'query':'handoff'}`}>{queryTask?'Query reply':'Stage action'}</span><span className="muted">{new Date(task.created_at).toLocaleDateString()}</span></div>
          <h2>{task.title}</h2><div className="muted">{task.project_code} · {task.project_title}</div><div className="task-stage">Current stage: <b>{stageNames[task.current_status]||task.current_status.replaceAll('_',' ')}</b></div>{queryTask&&task.detail&&<p>{task.detail}</p>}
        </div><button className="button" onClick={()=>openProject(task)}>Open project <ArrowRight size={14} style={{verticalAlign:'middle',marginLeft:5}}/></button>
      </article>;
    })}</div>}
  </div>;
}
