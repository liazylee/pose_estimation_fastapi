import {ActionIcon, Anchor, AppShell, Box, Group, NavLink, Title, useMantineColorScheme} from '@mantine/core';
import {Link, Outlet, useLocation} from 'react-router-dom';
import {Activity, Cloud, Moon, Sun, Upload, Video} from 'lucide-react';

export default function App() {
    const location = useLocation();
    const {colorScheme, toggleColorScheme} = useMantineColorScheme();
    const isActive = (to: string, exact = false) =>
        exact ? location.pathname === to : location.pathname.startsWith(to);

    return (
        <AppShell
            header={{height: 60}}
            navbar={{width: 240, breakpoint: 'sm'}}
            padding="md"
        >
            <AppShell.Header>
                <Group h="100%" px="md" justify="space-between">
                    <Group>
                        <Title order={4}>AI Video Analysis</Title>
                    </Group>
                    <Group gap="sm">
                        <Anchor component={Link} to="/upload" underline="never">upload</Anchor>
                        <Anchor href="/docs" target="_blank" rel="noreferrer" underline="never">API Docs</Anchor>
                        <ActionIcon variant="subtle" onClick={() => toggleColorScheme()}
                                    aria-label="Toggle color scheme">
                            {colorScheme === 'dark' ? <Sun size={18}/> : <Moon size={18}/>}
                        </ActionIcon>
                    </Group>
                </Group>
            </AppShell.Header>
            <AppShell.Navbar p="sm">
                <NavLink component={Link} to="/" label="dashboad" leftSection={<Activity size={16}/>}
                         active={isActive('/', true)}/>
                <NavLink component={Link} to="/upload" label="upload" leftSection={<Upload size={16}/>}
                         active={isActive('/upload')}/>
                <NavLink component={Link} to="/streams" label="Streams" leftSection={<Video size={16}/>}
                         active={isActive('/streams')}/>
                <NavLink component={Link} to="/dashboard" label="backend Dashboard" leftSection={<Cloud size={16}/>}/>
            </AppShell.Navbar>
            <AppShell.Main>
                <Box mx="auto" maw={1200} w="100%">
                    <Outlet/>
                </Box>
            </AppShell.Main>
        </AppShell>
    );
}


