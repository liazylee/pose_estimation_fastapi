import { AppShell, Group, NavLink, Title } from '@mantine/core';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Cloud, Upload, Activity, Video } from 'lucide-react';

export default function App() {
  const location = useLocation();
  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: 'sm' }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={4}>AI Video Analysis</Title>
          <Group gap="md">
            <Link to="/upload">上传</Link>
            <a href="/docs" target="_blank" rel="noreferrer">API Docs</a>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <NavLink component={Link} to="/" label="概览" leftSection={<Activity size={16} />} active={location.pathname === '/'} />
        <NavLink component={Link} to="/upload" label="上传" leftSection={<Upload size={16} />} active={location.pathname.startsWith('/upload')} />
        <NavLink component={Link} to="/streams" label="Streams" leftSection={<Video size={16} />} active={location.pathname.startsWith('/streams')} />
        <NavLink component={Link} to="/dashboard" label="后端Dashboard" leftSection={<Cloud size={16} />} />
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}


