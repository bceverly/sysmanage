import React from 'react';
import { Routes, Route } from "react-router-dom";

import './App.css';
import PrivateRoute from "./router/route"
import Navbar from "./components/Navbar/index";
import Dashboard from './pages/index';
import Hosts from './pages/hosts';
import Users from './pages/users';
import LogIn from './pages/login';
import LogOut from './pages/logout';

function App() {

  return (
    <div className="App">
      <Navbar />
      <Routes>
        <Route path="/login" element={<LogIn />} />
          <Route element={<PrivateRoute />}>
            <Route path="/" element={<Dashboard />} />
          </Route>
          <Route element={<PrivateRoute />}>
            <Route path="/hosts" element={<Hosts />} />
          </Route>
          <Route element={<PrivateRoute />}>
            <Route path="/users" element={<Users />} />
          </Route>
        <Route path="/logout" element={<LogOut />} />
      </Routes>
    </div>
  );
}

export default App;
