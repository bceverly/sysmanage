import React from 'react';
import { Outlet } from "react-router-dom";

import './App.css';
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import Navbar from "./Components/Navbar"
import Login from './Pages/Login';
import Home from './Pages/Home';
import Hosts from './Pages/Hosts';
import Users from './Pages/Users';
import Logout from './Pages/Logout';

function App() {
  return (
    <div className="App">
      <Router>
        <Navbar />
          <main className="main-content">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/" element={<Home />} />
              <Route path="/hosts" element={<Hosts />} />
              <Route path="/users" element={<Users />} />
              <Route path="/logout" element={<Logout />} />
            </Routes>
          </main>
      </Router>
    </div>
  );
}

export default App;
