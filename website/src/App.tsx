import React from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";

import './App.css';

//import AuthProvider from './hooks/AuthProvider';
import PrivateRoute from "./router/route.tsx"

import Navbar from "./components/Navbar/index.tsx";
import Dashboard from './pages/index.tsx';
import Hosts from './pages/hosts.tsx';
import Users from './pages/users.tsx';
import LogIn from './pages/login.tsx';
import LogOut from './pages/logout.tsx';

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Navbar />
        <Routes>
          <Route path="/login" element={<LogIn />} />
          <Route element={<PrivateRoute />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/hosts" element={<Hosts />} />
            <Route path="/users" element={<Users />} />
            <Route path="/logout" element={<LogOut />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
