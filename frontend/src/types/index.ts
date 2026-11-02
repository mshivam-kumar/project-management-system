export type User={id:string;name:string;email:string;designation:string;department:string|null;department_name?:string;verification_status:string;roles:string[]};
export type Project={id:string;project_code:string;title:string;description:string;department:string;department_name:string;created_by:string;created_by_name:string;estimated_amount:string;current_status:string;created_at:string;updated_at:string};
export type Activity={id:string;actor:string|null;actor_name:string;activity_type:string;message:string;created_at:string};
