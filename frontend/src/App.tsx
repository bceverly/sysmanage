import './App.css';
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import { ThemeProvider, createTheme } from '@mui/material/styles';
import darkScrollbar from '@mui/material/darkScrollbar';
import CssBaseline from '@mui/material/CssBaseline';
import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';

import Navbar from "./Components/Navbar"
import Login from './Pages/Login';
import Home from './Pages/Home';
import Hosts from './Pages/Hosts';
import Users from './Pages/Users';
import Logout from './Pages/Logout';

function App() {
  const darkTheme = createTheme({
    palette: {
      mode: 'dark',
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: (themeParam) => ({
          body: themeParam.palette.mode === 'dark' ? darkScrollbar() : null,
        }),
      },
    },
  });

  return (
    <div className="App">
      <ThemeProvider theme={darkTheme}>
        <CssBaseline enableColorScheme/>
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
      </ThemeProvider>
    </div>
  );
}

export default App;
