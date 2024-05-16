import React from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";

import './App.css';

//import AuthProvider from './hooks/AuthProvider';
import PrivateRoute from "./router/route"

import Navbar from "./components/Navbar";
import Dashboard from './pages';
import Hosts from './pages/hosts';
import Users from './pages/users';
import LogIn from './pages/login';
import LogOut from './pages/logout';

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
