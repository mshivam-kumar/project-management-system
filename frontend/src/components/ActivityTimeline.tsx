import type {Activity} from '../types';

type Props={activities?:Activity[];isLoading:boolean;isError:boolean;onDownload:(url:string,name:string)=>void};
type EventKind='request'|'approval'|'handoff'|'query'|'document'|'committee'|'note'|'update';

const styles:Record<EventKind,{label:string;className:string}>={
  request:{label:'Request',className:'request'},
  approval:{label:'Approval',className:'approval'},
  handoff:{label:'Handoff',className:'handoff'},
  query:{label:'Query / reply',className:'query'},
  document:{label:'Document',className:'document'},
  committee:{label:'Committee',className:'committee'},
  note:{label:'Note',className:'note'},
  update:{label:'Update',className:'update'},
};

function eventKind(activity:Activity):EventKind{
  const type=activity.activity_type.toUpperCase();
  const text=activity.message.toLowerCase();
  if(/query|repl(y|ied)/.test(text))return 'query';
  if(type.includes('FORWARD'))return 'handoff';
  if(type.includes('APPROV'))return 'approval';
  if(type.includes('DOCUMENT')||/uploaded|attached/.test(text))return 'document';
  if(type.includes('COMMITTEE')||/committee|board formed/.test(text))return 'committee';
  if(/approval|approved|acknowledged|accepted/.test(text))return 'approval';
  if(/forwarded|→|->/.test(text))return 'handoff';
  if(type.includes('SUBMIT')||type.includes('CREAT')||/submitted|created the project/.test(text))return 'request';
  if(type==='MESSAGE')return 'note';
  return 'update';
}

function stageTransition(message:string){
  const match=message.match(/(?:^|\.\s*)([^.]+?)\s*(?:→|->)\s*([^.]+?)(?:\.\s|$)/);
  return match?.[2]?.trim().replace(/[.!]+$/,'')||null;
}

export default function ActivityTimeline({activities,isLoading,isError,onDownload}:Props){
  if(isLoading)return <div className="muted">Loading activity…</div>;
  if(isError)return <div className="muted">Unable to load timeline.</div>;
  if(!activities?.length)return <div className="muted">No activity yet.</div>;

  return <div className="activity-timeline">
    {activities.map((activity,index)=>{
      const stage=stageTransition(activity.message);
      const kind=styles[eventKind(activity)];
      const initialStage=index===0&&!stage&&activity.activity_type==='PROJECT_CREATED';
      return <div className="activity-group" key={activity.id}>
        {(stage||initialStage)&&<div className="stage-start"><span className="stage-start__dot"/><span>Stage begins</span><strong>{stage||'Requirement / Draft'}</strong></div>}
        <article className={`timeline-item timeline-item--${kind.className}`}>
          <div className="timeline-item__meta"><span className={`activity-badge activity-badge--${kind.className}`}>{kind.label}</span><time>{new Date(activity.created_at).toLocaleString()}</time></div>
          <div className="timeline-item__actor"><b>{activity.actor_name}</b>{activity.actor_designation&&<span>{activity.actor_designation}</span>}</div>
          <p>{activity.message}</p>
          {activity.documents?.map(document=><div key={document.id}><button className="icon-button" onClick={()=>onDownload(document.url,document.name)}>Download {document.name}</button></div>)}
        </article>
      </div>;
    })}
  </div>;
}
