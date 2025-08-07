import React from 'react';
import ReactDOM from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import App from './App';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import TaskDetail from './pages/TaskDetail';
import Streams from './pages/Streams';

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'upload', element: <Upload /> },
      { path: 'tasks/:taskId', element: <TaskDetail /> },
      { path: 'streams', element: <Streams /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider defaultColorScheme="dark">
      <Notifications position="top-right" />
      <RouterProvider router={router} />
    </MantineProvider>
  </React.StrictMode>
);


