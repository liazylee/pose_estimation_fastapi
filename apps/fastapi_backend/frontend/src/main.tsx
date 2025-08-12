import React from 'react';
import ReactDOM from 'react-dom/client';
import {createBrowserRouter, RouterProvider} from 'react-router-dom';
import {MantineProvider, createTheme} from '@mantine/core';
import {Notifications} from '@mantine/notifications';
// Mantine styles
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import App from './App';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import TaskDetail from './pages/TaskDetail';
import Streams from './pages/Streams';

const router = createBrowserRouter([
    {
        path: '/',
        element: <App/>,
        children: [
            {index: true, element: <Dashboard/>},
            {path: 'upload', element: <Upload/>},
            {path: 'tasks/:taskId', element: <TaskDetail/>},
            {path: 'streams', element: <Streams/>},
        ],
    },
], {
    // 添加 basename 配置
    basename: '/app'
});

const theme = createTheme({
  fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, "Apple Color Emoji", "Segoe UI Emoji"',
  defaultRadius: 'md',
  primaryColor: 'blue',
  colors: {
    // keep Mantine defaults but can add custom palette later
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <MantineProvider defaultColorScheme="dark" theme={theme}>
            <Notifications position="top-right"/>
            <RouterProvider router={router}/>
        </MantineProvider>
    </React.StrictMode>
);