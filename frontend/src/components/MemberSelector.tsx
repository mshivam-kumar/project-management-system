import './WorkflowUi.css';

type Employee = Record<string, any>;

export default function MemberSelector({
  employees,
  name = 'member_ids',
  label,
  help,
  ariaLabel,
  defaultSelectedIds = [],
}: {
  employees: Employee[];
  name?: string;
  label: string;
  help?: string;
  ariaLabel: string;
  defaultSelectedIds?: string[];
}) {
  return (
    <fieldset className="member-selector" aria-required="true">
      <legend>{label}</legend>
      {help && <div className="muted member-selector-help">{help}</div>}
      <div className="member-selector-list">
        {employees.map(person => (
          <label className="member-selector-option" key={person.id}>
            <input
              type="checkbox"
              name={name}
              value={person.id}
              defaultChecked={defaultSelectedIds.includes(person.id)}
              aria-label={`${ariaLabel}: ${person.name}`}
            />
            <span>
              <b>{person.name}</b>
              <small>
                {person.employee_id || person.email || ''}
                {person.roles?.some((role: string) => ['ADMIN', 'SUPER_ADMIN'].includes(role))
                  ? ' · Admin'
                  : ''}
                {person.roles?.includes('IA_WING') ? ' · IA Wing' : ''}
              </small>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
