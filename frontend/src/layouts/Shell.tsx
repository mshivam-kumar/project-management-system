import { useQuery } from '@tanstack/react-query';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Bell,
  BriefcaseBusiness,
  Building2,
  ClipboardList,
  FileClock,
  LogOut,
  Settings,
  Store,
  Users,
} from 'lucide-react';
import type { User } from '../types';
import { api } from '../services/api';

export default function Shell({
  user,
  onLogout,
  children,
}: {
  user: User;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const roles = user.roles || [];
  const displayRoles = roles.map(role => role === 'IA_WING' ? 'IA Wing' : role);
  const admin = roles.includes('ADMIN') || roles.includes('SUPER_ADMIN');
  const superAdmin = roles.includes('SUPER_ADMIN');
  const navigate = useNavigate();
  const notices = useQuery({
    queryKey: ['notifications', user.id],
    queryFn: async () => {
      const response = await api.get('/notifications/');
      return response.data.results || [];
    },
  });
  const unread = notices.data?.filter((notice: { is_read: boolean }) => !notice.is_read).length || 0;
  type NavigationItem = [string, typeof BriefcaseBusiness, string];
  const links: NavigationItem[] = [
    ['Projects', BriefcaseBusiness, '/projects'],
    ['My Tasks', ClipboardList, '/tasks'],
    ['Notifications', Bell, '/notifications'],
  ];
  if (admin) {
    links.push(
      ['User Management', Users, '/users'],
      ['Departments', Building2, '/departments'],
      ['Vendor Management', Store, '/vendors'],
      ['Audit Logs', FileClock, '/audit'],
    );
  }
  if (superAdmin) {
    links.push(
      ['Admin Management', Users, '/admins'],
      ['System Settings', Settings, '/settings'],
    );
  }

  async function logout() {
    try {
      const refresh = sessionStorage.getItem('refresh');
      if (refresh) await api.post('/auth/logout/', { refresh });
    } finally {
      onLogout();
    }
  }

  return (
    <div className="app shell">
      <aside className="sidebar">
        <div className="brand">Procure<span style={{ color: '#3974d8' }}>Flow</span></div>
        <nav className="nav">
          {links.map(([label, Icon, path]) => (
            <NavLink key={path} to={path}>
              <Icon size={17} />
              {label}
              {label === 'Notifications' && unread > 0 && (
                <span className="status" style={{ marginLeft: 'auto' }}>{unread}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={logout}
          className="nav"
          style={{
            position: 'absolute',
            bottom: 22,
            border: 0,
            background: 'none',
            color: '#718096',
            display: 'flex',
            flexDirection: 'row',
            padding: 12,
            cursor: 'pointer',
          }}
        >
          <LogOut size={17} />
          Sign out
        </button>
      </aside>
      <main className="main">
        <header className="topbar">
          <div style={{ fontWeight: 650 }}>Procurement workspace</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <button
              aria-label="Open notifications"
              onClick={() => navigate('/notifications')}
              className="icon-button"
              style={{ position: 'relative', background: 'transparent' }}
            >
              <Bell size={18} color="#718096" />
              {unread > 0 && (
                <span
                  style={{
                    position: 'absolute',
                    right: 2,
                    top: 2,
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: '#3974d8',
                  }}
                />
              )}
            </button>
            <div>
              <b style={{ fontSize: 13 }}>{user.name}</b>
              <div className="muted" style={{ fontSize: 11 }}>{displayRoles.join(', ') || 'USER'}</div>
            </div>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
